import time


msgCount = 0            # count of outgoing messages
interval = 2000          # interval between sends
lastSendTime = 0        # time of last packet send


def setSpread(lora):
 
    print("LoRa Duplex - Set spreading factor")
    lora.setSpreadingFactor(8)           # ranges from 6-12,default 7 see API docs
    
    do_loop(lora)


def do_loop(lora):    
    
    lastSendTime = time.ticks_ms()
    interval = (lastSendTime % 2000) + 1000
    global msgCount

    while True:
        if (time.ticks_ms() - lastSendTime > interval):
            message = "HeLoRa World! {}".format(msgCount)
            sendMessage(lora, message)
            print("Sending message:\n{}\n".format(message))
            lastSendTime = time.ticks_ms()          # timestamp the message
            interval = (lastSendTime % 2000) + 1000    # 2-3 seconds
            msgCount += 1

        # parse for a packet, and call onReceive with the result:
        onReceive(lora, lora.parsePacket()) 
    

def sendMessage(lora, outgoing):
    lora.beginPacket()                  # start packet
    lora.print(outgoing)
    lora.endPacket()                    # finish packet and send it 
    

def onReceive(lora, packetSize):
    if (packetSize == 0):
        return          # if there's no packet, return

    # read packet
    payload = bytearray()

    while (lora.available()):
        b = lora.read()
        if b: payload.append(b)

    print("*** Received message ***\n{}".format(bytes(payload).decode()))
    print("RSSI: {}".format(str(lora.packetRssi())))
    print("Snr: {}\n".format(str(lora.packetSnr()))) 
