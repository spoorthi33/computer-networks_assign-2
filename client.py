import os
import sys
import time
import pickle
import socket
import threading
from library import *

SERVER_IP = sys.argv[1]
if __name__ == "__main__":
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(SOCKET_BLOCKING_TIMEOUT)
    packet = create_packet(CONNECTION_ESTABLISHMENT_REQUEST, "", CLIENT_PORT, SERVER_PORT, None, None)
    send_packet(packet, sock, SERVER_IP, SERVER_PORT)
    sent_time = time.time()
    while True:
        try:
            data , addr = sock.recvfrom(MAX_PACKET_SIZE) # timeout for recvfrom is SOCKET_BLOCKING_TIMEOUT
        except socket.timeout as e:
            print(e)
            if time.time() - sent_time > TIMEOUT_TO_RETRANSMIT: # timed out
                send_packet(packet, sock, SERVER_IP, SERVER_PORT)
            continue
        received_packet = pickle.loads(data)
        if received_packet['opcode'] == ACKNOWLEDGEMENT:
            print('received ack for CONNECTION_ESTABLISHMENT_REQUEST')
            break
        else:
            print(f'Expected ack packet, ignoring received packet 1: {received_packet}')

    while True:
        user_command = input('Enter command: ')
        command_split = user_command.split()

        if user_command.lower() == "exit":
            packet = create_packet(CONNECTION_TERMINATION_REQUEST, "", CLIENT_PORT, SERVER_PORT, None, None)
            send_packet(packet, sock, SERVER_IP, SERVER_PORT)
            # sent_time = time.time()
            # while True:
            #     try:
            #         data , addr = sock.recvfrom(MAX_PACKET_SIZE) # timeout for recvfrom is SOCKET_BLOCKING_TIMEOUT
            #     except socket.timeout as e:
            #         print(e)
            #         if time.time() - sent_time > TIMEOUT_TO_RETRANSMIT: # timed out
            #             send_packet(packet, sock, SERVER_IP, SERVER_PORT)
            #         continue
            #     received_packet = pickle.loads(data)
            #     if received_packet['opcode'] == ACKNOWLEDGEMENT:
            #         print('received ack for FILE_UPLOAD_REQUEST')
            #         break
            #     else:
            #         print(f'Expected ack packet, ignoring received packet: {received_packet}')
            # ack_packet  = create_packet(ACKNOWLEDGEMENT, "", CLIENT_PORT, SERVER_PORT, None, None)
            # send_packet(ack_packet, sock, SERVER_IP, SERVER_PORT)

            sock.close()
            sys.exit()
        
        elif user_command.lower() == "help":
            print("Available commands:")
            print("\tupload {filename}")
            print("\tdownload {filename}")
            print("\texit")

        elif command_split[0] == "upload":
            try:
                filename = command_split[1]
            except Exception as e:
                print(f'Error: {e}')
                continue

            if not os.path.exists(filename):
                print(f'file {filename} to be uploaded does not exist')

            upload_file_size = os.path.getsize(filename)

            number_of_packets = upload_file_size // CHUNK_SIZE
            if upload_file_size % CHUNK_SIZE != 0:
                number_of_packets += 1

            packet = create_packet(FILE_UPLOAD_REQUEST, f"{number_of_packets}", CLIENT_PORT, SERVER_PORT, filename, None)
            send_packet(packet, sock, SERVER_IP, SERVER_PORT)
            sent_time = time.time()

            while True:
                try:
                    data , addr = sock.recvfrom(MAX_PACKET_SIZE) # timeout for recvfrom is SOCKET_BLOCKING_TIMEOUT
                except socket.timeout as e:
                    print(e)
                    if time.time() - sent_time > TIMEOUT_TO_RETRANSMIT: # timed out
                        send_packet(packet, sock, SERVER_IP, SERVER_PORT)
                    continue
                received_packet = pickle.loads(data)
                if received_packet['opcode'] == ACKNOWLEDGEMENT:
                    print('received ack for FILE_UPLOAD_REQUEST')
                    break
                else:
                    print(f'Expected ack packet, ignoring received packet 2: {received_packet}')

            upload_start_time = time.time()

            thread_send_file = threading.Thread(target=send_file, args=(filename, sock, CLIENT_PORT, SERVER_IP, SERVER_PORT))
            thread_receive_acks = threading.Thread(target=receive_acks, args=(sock, CLIENT_PORT, SERVER_IP, SERVER_PORT, number_of_packets))

            thread_send_file.start()
            thread_receive_acks.start()
            thread_send_file.join()
            thread_receive_acks.join()

            upload_end_time = time.time()
            upload_total_time = upload_end_time - upload_start_time
            throughput = (upload_file_size * 8)/upload_total_time
            print(f'throughput: {throughput} bits per second')
            print(f'time taken for upload: {upload_total_time} seconds')
            
        elif command_split[0] == "download":
            try:
                filename = command_split[1]
            except Exception as e:
                print(f'Error: {e}')
                continue

            packet = create_packet(FILE_DOWNLOAD_REQUEST, "", CLIENT_PORT, SERVER_PORT, filename, None)
            send_packet(packet, sock, SERVER_IP, SERVER_PORT)
            sent_time = time.time()
            while True:
                try:
                    data , addr = sock.recvfrom(MAX_PACKET_SIZE) # timeout for recvfrom is SOCKET_BLOCKING_TIMEOUT
                except socket.timeout as e:
                    print(e)
                    if time.time() - sent_time > TIMEOUT_TO_RETRANSMIT: # timed out
                        send_packet(packet, sock, SERVER_IP, SERVER_PORT)
                    continue
                received_packet = pickle.loads(data)
                if received_packet['opcode'] == ACKNOWLEDGEMENT:
                    print(f'received ack for FILE_DOWNLOAD_REQUEST: {received_packet}')
                    break
                else:
                    print(f'Expected ack packet, ignoring received packet 3: {received_packet}')

            receive_file(filename, sock, CLIENT_PORT, SERVER_IP, SERVER_PORT, int(received_packet['DataBody']))
        else:
            print('Error: Command not supported')
