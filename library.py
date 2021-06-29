import time
import pickle
import socket
import hashlib
import threading

# Size limits
CHUNK_SIZE = 256
WINDOW_SIZE = 5
FRAME_SIZE = 5
MAX_PACKET_SIZE = 512

# opcodes defined in protocol specification
ERROR_PACKET = 0 # corrupt , cannot be fulfilled etc, details(type of error, seqno) in data part 
FILE_UPLOAD_REQUEST = 1
FILE_DOWNLOAD_REQUEST = 2
ACKNOWLEDGEMENT = 3
REGULAR_DATA_TRANSFER = 4
CONNECTION_ESTABLISHMENT_REQUEST = 5
CONNECTION_TERMINATION_REQUEST = 6

# time limits
TIMEOUT_TO_RETRANSMIT = 1
SOCKET_BLOCKING_TIMEOUT = 1
# TIMEOUT_TO_RETRANSMIT = 100
# SOCKET_BLOCKING_TIMEOUT = 100

# ports
SERVER_PORT = 1420
CLIENT_PORT = 5000

lock = threading.Lock()

# sender side global vars
window_position = 0
positive_acks = []
negative_acks = []

# receiver side global vars
frame_position = 0
receiver_buffer = {}

# def calculate_checksum(*args):
#     m = hashlib.md5()
#     for arg in args:
#         m.update(arg.encode())
#     return m.hexdigest()

def to_bytes(s):
    if type(s) is bytes:
        return s
    elif type(s) is str:
        return s.encode()
    else:
        raise TypeError(f"Expected bytes or string, but got {type(s)}")

def create_packet(opcode, data_chunk, source_port, destination_port, filename = None, seqno = None):
    packet = {}
    datagram_header = {}
    datagram_header['port_s'] = source_port
    datagram_header['port_d'] = destination_port
    datagram_header['length'] = len(data_chunk)
    datagram_header['checksum'] = hashlib.md5(to_bytes(data_chunk)).hexdigest()
    packet['header'] = datagram_header
    packet['opcode'] = opcode
    packet['TID'] = destination_port
    packet['SeqNo'] = seqno
    packet['FileName'] = filename
    packet['DataBody'] = data_chunk

    return packet

def verify_checksum(packet):
    # to_be_hashed = packet['length'] + packet['source_port'] + packet['destination_port'] + packet['body']
    checksum = hashlib.md5(to_bytes(packet['DataBody'])).hexdigest()
    return checksum == packet['header']['checksum']

def file2packets(filename, source_port, destination_port):
    packets = []
    seqno = 0
    with open(filename, 'rb') as f:
        while (data_chunk := f.read(CHUNK_SIZE)):
            packet = create_packet(REGULAR_DATA_TRANSFER, data_chunk, source_port, destination_port, filename, seqno)
            packets.append(packet)
            seqno += 1
    
    # print(f'LENGTH OF PACKETS: {len(packets)}')

    return packets

def send_packet(packet, sock, destination_ip, destination_port):
    print(f'sending packet: {packet}')
    sock.sendto(pickle.dumps(packet), (destination_ip, destination_port))

def send_file(filename, sock, source_port, destination_ip, destination_port):
    global window_position
    # print('Entered send file function')
    packets = file2packets(filename, source_port, destination_port)
    # print('File converted to packets and saved in list')
    sent_timestamps = [None] * len(packets)

    while True:
        with lock:
            # print('lock acquired by send_file')
            if window_position >= len(packets):
                eof_packet = create_packet(REGULAR_DATA_TRANSFER, "eof", source_port, destination_port, filename, None)
                send_packet(eof_packet, sock, destination_ip, destination_port)
                window_position = 0
                positive_acks.clear()
                negative_acks.clear()
                break

            rangeend = window_position + WINDOW_SIZE
            if window_position + WINDOW_SIZE > len(packets):
                rangeend = len(packets)

            for seqno in range(window_position, rangeend):
                if seqno in positive_acks:
                    # print(f'seqno {seqno} found in acks, continuing')
                    continue

                if sent_timestamps[seqno] is not None:
                    if (time.time() - sent_timestamps[seqno] <= TIMEOUT_TO_RETRANSMIT): # in time
                        if seqno in negative_acks: # resend -ve ack
                            send_packet(packets[seqno], sock, destination_ip, destination_port)
                            # print('sent packet: {packets[seqno]}')
                            sent_timestamps[seqno] = time.time()
                            negative_acks.remove(seqno)
                        else:
                            # print('waiting for ack or timeout to occur')
                            continue
                    else: # timed out # resend
                        send_packet(packets[seqno], sock, destination_ip, destination_port)
                        # print('sent packet: {packets[seqno]}')
                        sent_timestamps[seqno] = time.time()
                else:
                    send_packet(packets[seqno], sock, destination_ip, destination_port)
                    # print('sent packet: {packets[seqno]}')
                    sent_timestamps[seqno] = time.time()

            if window_position in positive_acks: # negative acks also should probably trigger this, but ignoring for now
                temp = window_position
                while temp in positive_acks:
                    window_position += 1
                    temp += 1
                

def receive_file(filename, sock, source_port, destination_ip, destination_port, number_of_packets):
    global frame_position
    packets_written_to_file = []
    last_received__inorder_packet_seqno = -1

    while True:
        try:
            data , addr = sock.recvfrom(MAX_PACKET_SIZE)
        except socket.timeout as e:
            continue
        packet = pickle.loads(data)
        seqno = packet['SeqNo']
        if verify_checksum(packet): # send +ve ack
            ack_packet_data = ""
            if packet['DataBody'] == "eof":
                ack_packet_data = "eof"
            if len(packets_written_to_file) == number_of_packets and seqno is None:
                frame_position = 0
                receiver_buffer.clear()
                break
            positive_ack_packet = create_packet(ACKNOWLEDGEMENT, ack_packet_data, source_port, destination_port, filename=None, seqno=seqno)
            send_packet(positive_ack_packet, sock, destination_ip, destination_port)
            print(f'sending packet from receive file: {packet}')

            if packet['DataBody'] == 'eof': # end of file
                print('file received')
                break

            if seqno is not None:
                if (seqno >= frame_position) and (seqno < frame_position + FRAME_SIZE): 
                    # packets out of frame are ignored, they will be resent by client once they timeout on client side
                    if seqno == last_received__inorder_packet_seqno + 1: # next packet in order received
                        if seqno not in packets_written_to_file:
                            with open(filename, 'ab') as f:
                                f.write(packet['DataBody'])
                                packets_written_to_file.append(seqno)
                                last_received__inorder_packet_seqno = seqno
                                frame_position += 1
                            temp = seqno + 1
                            while temp in receiver_buffer:
                                with open(filename, 'ab') as f:
                                    f.write(receiver_buffer[temp]['DataBody'])
                                    packets_written_to_file.append(temp)
                                    receiver_buffer.pop(temp)
                                    last_received__inorder_packet_seqno = temp
                                    frame_position += 1
                                temp += 1
                        
                    else: # not in order, place in buffer
                        receiver_buffer[seqno] = packet
        else: # send -ve ack
            if seqno:
                negative_ack_packet = create_packet(ERROR_PACKET, "Checksum mismatch", source_port, destination_ip, filename=None, seqno=seqno)
                send_packet(negative_ack_packet, sock, destination_ip, destination_port)
            else:
                positive_ack_packet = create_packet(ACKNOWLEDGEMENT, "", source_port, destination_port, filename=None, seqno=seqno)
                send_packet(positive_ack_packet, sock, destination_ip, destination_port)

def receive_acks(sock, source_port, destination_ip, destination_port,number_of_packets):
    while True:
        if len(positive_acks) == number_of_packets:
            break
        try:
            data , addr = sock.recvfrom(MAX_PACKET_SIZE)
        except socket.timeout as e:
            print(e)
            continue
        packet = pickle.loads(data)
        with lock:
            print(f'received ack packet: {packet}')
            # print('lock acquired by receive_acks')
            if packet['SeqNo'] is not None:
                if packet['opcode'] == ACKNOWLEDGEMENT: # +ve ack received
                    print('ack received found to be +ve')
                    positive_acks.append(packet['SeqNo'])
                elif packet['opcode'] == ERROR_PACKET: # -ve ack received
                    print('ack received found to be -ve')
                    negative_acks.append(packet['SeqNo'])
            else:
                if packet['opcode'] == FILE_DOWNLOAD_REQUEST:
                    ack_packet = create_packet(ACKNOWLEDGEMENT, f"{number_of_packets}", source_port, destination_port, None, None)
                    send_packet(ack_packet, sock, destination_ip, destination_port)
                # ignoring ack packets other than that of eof, if they dont have seqno
                if packet['DataBody'] == "eof":
                    print('ack received for eof')
                    break
