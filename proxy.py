#!/usr/bin/env python3

import json
import os
from socket import *
from threading import Thread
import sys
import uuid

# TCP Proxy Structure:
# _________________________________________________________
# main () ... opens proxy socket and starts the proxyThread
# | - > findClients () ... waits for clients to connect and starts clientThread
#       | - >   handleRequests () ... sends messages from client -> proxy -> server
#               | - - - > fetchHost() ... parse client's message for address and port (helper method)
#               | - - -> editHeader() ... edit client's message before sending it to server (helper method)
#               | - > sendResponses() ... sends messages from server -> proxy -> client [NON-CONNECT]
#               | - - -> connection() ... opens connection between two sockets [CONNECT]
#               |
#               | - - -> logMessage() ... (helper method)

# Method to log messages to a json file
def logMessage(msgTitle, msgBody, logPath):
    data = json.load(open(logPath, 'r'))
    data[msgTitle] = msgBody
    json.dump(data, open(logPath, "w"), indent = 3)

# Method to send messages from
# server -> proxy -> client and
# client -> proxy -> server (CONNECT)
def connection(socket_rcv, socket_snd):
    while True:
        try:
            socket_snd.sendall(socket_rcv.recv(2048))
        except Exception:
            socket_rcv.close()
            socket_snd.close()
            break

# Method to send messages from
# server -> proxy -> client (browser)
def sendResponses(serverSocket, clientSocket, logPath=None):
    while True:
        try:
            packet = serverSocket.recv(2048)
            if packet and logPath is not None:
                data_packet = packet.decode("utf-8","backslashreplace")
                logMessage("Server response received",data_packet,logPath)
            clientSocket.sendall(packet)
        except Exception:
            serverSocket.close()
            clientSocket.close()
            break

# Method to edit the header
def editHeader(clientRequest, logPath=None):

    header = clientRequest.decode("utf-8","backslashreplace")
    header = header.replace("HTTP/1.1", "HTTP/1.0")
    header = header.replace("keep-alive", "close")
    
    if logPath is not None:
        logMessage("Modified header",header,logPath)

    return header

# Method to find (hostAddress, hostPort) from a request header
def fetchHost(line_set):
    # HOST: <address>:<port>
    # HOST: <address>
    hostAddress = None
    for line in line_set:
        temp = line.lstrip()
        if temp[:4].lower() == 'host':
            hostAddress = line[line.find(':') + 1:].lstrip().rstrip() #HOST:[<address>:<port>] || HOST:[<address>]

            indexOne = hostAddress.find(':')
            if indexOne != -1:
                return hostAddress[:indexOne], int(hostAddress[indexOne + 1:].lstrip().rstrip()) #HOST:<address>:[<port>]
            else:
                break
            
    # GET <http/s>:<address>:<port>
    # GET <http/s>:<address>
    # GET <address>:<port>
    # GET <address>
    tempString = line_set[0]
    indexTwo = line_set[0].find(':')
    while indexTwo != -1:
        tempString = tempString[indexTwo + 1:].lstrip().rstrip()
        if tempString.isnumeric():
            return hostAddress, int(tempString) 
        indexTwo = tempString.find(':')     
    
    # http  = 80
    # https = 403
    if line_set[0].find('https://') != -1:
        return hostAddress, 403
    return hostAddress, 80

# messages from client (browser) -> proxy -> server
def handleRequests(clientSocket, addr, logPath=None):
    while True:
        request = clientSocket.recv(2048)
        if request:
            header = request.decode("utf-8","backslashreplace")
    
            line_set = header.splitlines()
            print(addr[0], '>>> ', line_set[0][:line_set[0].lower().find('http/')])

            # parse the request to find address and port of host
            hostAddress, hostPort = fetchHost(line_set)
            serverSocket = socket(AF_INET, SOCK_STREAM)

            if logPath is not None and hostAddress is not None:
                # Directory
                dir_path = os.path.join(logPath, hostAddress)
                if not os.path.isdir(dir_path):
                    try:
                        os.mkdir(dir_path)
                    except Exception:
                        pass
                # File
                this_uuid = str(uuid.uuid1())
                file_name = hostAddress + '.' + this_uuid + '.json'
                logPath = os.path.join(dir_path, file_name)
                # Data
                dictionary = {
                    "Incoming header" : header,
                }
                json_object = json.dumps(dictionary, indent = 3)
                with open(logPath, "w") as outfile:
                    outfile.write(json_object)

            # respond to request
            if line_set[0].lower().find('connect') != -1: #if CONNECT
                # get the response
                response = "HTTP/1.0 200 OK\r\n\r\n"
                exception = serverSocket.connect_ex((hostAddress, hostPort))
                if exception != 0:
                    response = "HTTP/1.0 502 Bad Gateway\r\n\r\n"
                clientSocket.send(response.encode("utf-8"))
                if logPath is not None:
                    logMessage("Proxy response sent","HTTP/1.0 200 OK\r\n\r\n",logPath)
                if exception != 0:
                    break
                
                # establish two-way connection
                serverThread = Thread(target=connection, args=(serverSocket,clientSocket), daemon=True)
                clientThread = Thread(target=connection, args=(clientSocket,serverSocket), daemon=True)
                serverThread.start()
                clientThread.start()
                
            else: #if otherwise
                # establish connection with the host
                serverSocket.connect((hostAddress, hostPort))

                #send the response
                newHeader = editHeader(request, logPath)
                serverSocket.send(newHeader.encode('utf-8'))

                # send messages from the host to the client
                serverThread = Thread(target=sendResponses, args=(serverSocket,clientSocket,logPath), daemon=True)
                serverThread.start()
            
            break
        
# wait for clients to connect
def findClients(proxySocket, logPath=None):
    proxySocket.listen()
    while True:
        clientSocket, addr = proxySocket.accept()
        
        clientThread = Thread(target=handleRequests, args=(clientSocket, addr, logPath), daemon=True)
        clientThread.start()

if __name__ == '__main__':   
    serverPort = int(sys.argv[1])
    logPath = None

    if len(sys.argv) > 2 and sys.argv[2].lower() == 'log':
        logPath = os.path.join(os.getcwd(),'Log')
        if not os.path.isdir(logPath):
            os.mkdir(logPath)

    # proxy server:
    proxySocket = socket(AF_INET, SOCK_STREAM)
    proxySocket.bind((b'0.0.0.0', serverPort))

    proxyThread = Thread(target=findClients, args=(proxySocket,logPath), daemon=True)
    proxyThread.start()
    
    while True:
        text = sys.stdin.readline()
        if (not text):
            break
    
    proxySocket.close()