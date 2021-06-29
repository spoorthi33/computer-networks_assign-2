import os
import time
import pickle
import socket
from library import *

server_hostname = socket.gethostname()
server_ip = socket.gethostbyname(server_hostname)

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((server_ip, SERVER_PORT))
print(f'server started listening on {server_ip} at port {SERVER_PORT}')

while True:
    data , client = sock.recvfrom(MAX_PACKET_SIZE)
    packet = pickle.loads(data)
    client_ip = client[0]
    CLIENT_PORT = client[1] # overwrite defined CLIENT_PORT constant based on socket

    if packet['opcode'] == CONNECTION_ESTABLISHMENT_REQUEST:
        ack_packet = create_packet(ACKNOWLEDGEMENT, "CONNECTION_ESTABLISHMENT_REQUEST confirmed", SERVER_PORT, CLIENT_PORT, packet['FileName'], None)
        send_packet(ack_packet, sock, client_ip, CLIENT_PORT)
        continue
    elif packet['opcode'] == FILE_UPLOAD_REQUEST: # receive file
        ack_packet = create_packet(ACKNOWLEDGEMENT, "FILE_UPLOAD_REQUEST confirmed", SERVER_PORT, CLIENT_PORT, packet['FileName'], None)
        send_packet(ack_packet, sock, client_ip, CLIENT_PORT)
        receive_file(packet['FileName'], sock, SERVER_PORT, client_ip, CLIENT_PORT, int(packet['DataBody']))
    elif packet['opcode'] == FILE_DOWNLOAD_REQUEST: # send requested file to client
        if not os.path.exists(packet['FileName']):
            print(f'received download requested for a file that does not exist: {packet["FileName"]}')

        download_file_size = os.path.getsize(packet['FileName'])
        number_of_packets = download_file_size // CHUNK_SIZE
        if download_file_size % CHUNK_SIZE != 0:
            number_of_packets += 1
        download_start_time = time.time()
        ack_packet = create_packet(ACKNOWLEDGEMENT, f"{number_of_packets}", SERVER_PORT, CLIENT_PORT, packet['FileName'], None)
        send_packet(ack_packet, sock, client_ip, CLIENT_PORT)
        thread_send_file = threading.Thread(target=send_file, args=(packet['FileName'], sock, SERVER_PORT, client_ip, CLIENT_PORT))
        thread_receive_acks = threading.Thread(target=receive_acks, args=(sock, SERVER_PORT, client_ip, CLIENT_PORT, number_of_packets))

        thread_send_file.start()
        thread_receive_acks.start()
        thread_send_file.join()
        thread_receive_acks.join()

        download_end_time = time.time()
        download_total_time = download_end_time - download_start_time
        throughput = (download_file_size * 8)/download_total_time
        print(f'throughput: {throughput} bits per second')
        print(f'time taken for download: {download_total_time} seconds')

    elif packet['opcode'] == CONNECTION_TERMINATION_REQUEST:
        ack_packet = create_packet(ACKNOWLEDGEMENT, "CONNECTION_TERMINATION_REQUEST confirmed", SERVER_PORT, CLIENT_PORT, packet['FileName'], None)
        send_packet(ack_packet, sock, client_ip, CLIENT_PORT)
        # try:
        #     data, addr = sock.recvfrom(MAX_PACKET_SIZE)
        # except socket.timeout as e:
        #     print(e)
        # received_packet = pickle.loads(data)
        # if received_packet['opcode'] == ACKNOWLEDGEMENT:
        #     break
        # elif received_packet['opcode'] == CONNECTION_TERMINATION_REQUEST:
        #     continue
        # else:
        #     break
        break
    else:
        print(f'received packet: {packet}')

sock.close()
