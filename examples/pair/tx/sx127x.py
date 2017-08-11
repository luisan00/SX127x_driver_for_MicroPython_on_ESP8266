from time import sleep
from machine import Pin
import gc


LORA_DEFAULT_SS_PIN = 15
LORA_DEFAULT_RESET_PIN = 4
LORA_DEFAULT_DIO0_PIN = 5

PA_OUTPUT_RFO_PIN = 0
PA_OUTPUT_PA_BOOST_PIN = 1

# registers
REG_FIFO = 0x00
REG_OP_MODE = 0x01
REG_FRF_MSB = 0x06
REG_FRF_MID = 0x07
REG_FRF_LSB = 0x08
REG_PA_CONFIG = 0x09
REG_LNA = 0x0c
REG_FIFO_ADDR_PTR = 0x0d

REG_FIFO_TX_BASE_ADDR = 0x0e
# FifoTxBaseAddr = 0x00
FifoTxBaseAddr = 0x80

REG_FIFO_RX_BASE_ADDR = 0x0f  
FifoRxBaseAddr = 0x00 
REG_FIFO_RX_CURRENT_ADDR = 0x10
REG_IRQ_FLAGS = 0x12
REG_RX_NB_BYTES = 0x13
REG_PKT_RSSI_VALUE = 0x1a
REG_PKT_SNR_VALUE = 0x1b
REG_MODEM_CONFIG_1 = 0x1d
REG_MODEM_CONFIG_2 = 0x1e
REG_PREAMBLE_MSB = 0x20
REG_PREAMBLE_LSB = 0x21
REG_PAYLOAD_LENGTH = 0x22
REG_FIFO_RX_BYTE_ADDR = 0x25
REG_MODEM_CONFIG_3 = 0x26
REG_RSSI_WIDEBAND = 0x2c
REG_DETECTION_OPTIMIZE = 0x31
REG_DETECTION_THRESHOLD = 0x37
REG_SYNC_WORD = 0x39
REG_DIO_MAPPING_1 = 0x40
REG_VERSION = 0x42

# modes
MODE_LONG_RANGE_MODE = 0x80  # bit 7: 1 => LoRa mode
MODE_SLEEP = 0x00
MODE_STDBY = 0x01
MODE_TX = 0x03
MODE_RX_CONTINUOUS = 0x05
MODE_RX_SINGLE = 0x06

# PA config
PA_BOOST = 0x80

# IRQ masks
IRQ_TX_DONE_MASK = 0x08
IRQ_PAYLOAD_CRC_ERROR_MASK = 0x20
IRQ_RX_DONE_MASK = 0x40
IRQ_RX_TIME_OUT_MASK = 0x80

# Buffer size
MAX_PKT_LENGTH = 256


class SX127x:
        
    def __init__(self, spi,
                 ss_pin_id = LORA_DEFAULT_SS_PIN, reset_pin_id = LORA_DEFAULT_RESET_PIN, dio0_pin_id = LORA_DEFAULT_DIO0_PIN,
                 frequency = 433E6, tx_power_level = 2, 
                 signal_bandwidth = 125E3, spreading_factor = 8, coding_rate = 5,
                 preamble_length = 8, implicitHeaderMode = False, sync_word = 0x12, enable_CRC = False,
                 onReceive = None,):
                 
        self._spi = spi
        self._ss = Pin(ss_pin_id, Pin.OUT)
        self._reset = Pin(reset_pin_id, Pin.OUT)
        self._irq = Pin(dio0_pin_id, Pin.IN)
        
        self._packetIndex = 0
        self._onReceive = onReceive

        # perform reset
        self._reset.value(0)
        sleep(0.01)
        self._reset.value(1)
        sleep(0.01)

        # start SPI        
        self._ss.value(1)
        self._spi.init()  

        # check version
        version = self.readRegister(REG_VERSION)        
        if version != 0x12: return None
            
        
        # put in LoRa and sleep mode
        self.sleep()
        
        
        # config
        self.setFrequency(frequency)
        self.setSignalBandwidth(signal_bandwidth) 

        # set LNA boost
        self.writeRegister(REG_LNA, self.readRegister(REG_LNA) | 0x03)

        # set auto AGC
        self.writeRegister(REG_MODEM_CONFIG_3, 0x04)

        self.setTxPower(tx_power_level)         
        self._implicitHeaderMode = implicitHeaderMode
        if implicitHeaderMode: self.implicitHeaderMode()        
        self.setSpreadingFactor(spreading_factor)
        self.setCodingRate(coding_rate)
        self.setPreambleLength(preamble_length)
        # self.setSyncWord(sync_word)        
        if enable_CRC: self.enableCRC()
        
        # set base addresses
        self.writeRegister(REG_FIFO_TX_BASE_ADDR, FifoTxBaseAddr)
        self.writeRegister(REG_FIFO_RX_BASE_ADDR, FifoRxBaseAddr)
        
        self.standby() 
         

    def beginPacket(self, implicitHeader = False):
        
        self.standby()

        if implicitHeader:
            self.implicitHeaderMode()
        else:
            self.explicitHeaderMode() 

        # reset FIFO address and paload length 
        self.writeRegister(REG_FIFO_ADDR_PTR, FifoTxBaseAddr)
        self.writeRegister(REG_PAYLOAD_LENGTH, 0) 
         
        return True
     

    def endPacket(self):
        # put in TX mode
        self.writeRegister(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_TX)

        # wait for TX done, standby automatically on TX_DONE
        while (self.readRegister(REG_IRQ_FLAGS) & IRQ_TX_DONE_MASK) == 0:
            pass 
            
        # clear IRQ's
        self.writeRegister(REG_IRQ_FLAGS, IRQ_TX_DONE_MASK) 
        
        self.collect_garbage()
        return True
     

    def collect_garbage(self):
        gc.collect()
        print('[Memory - free: {}   allocated: {}]'.format(gc.mem_free(), gc.mem_alloc()))
        
        
    def packetRssi(self):
        return (self.readRegister(REG_PKT_RSSI_VALUE) - ( 164 if self._frequency < 868E6 else 157))


    def packetSnr(self):
        return (self.readRegister(REG_PKT_SNR_VALUE)) * 0.25

        
    def print(self, string):
        return self.write(string.encode())
        

    def write(self, buffer):
        currentLength = self.readRegister(REG_PAYLOAD_LENGTH)
        size = len(buffer)

        # check size
        if (currentLength + size) > (MAX_PKT_LENGTH - FifoTxBaseAddr) :
            size = (MAX_PKT_LENGTH - FifoTxBaseAddr) - currentLength 

        # write data
        for i in range(size):
            self.writeRegister(REG_FIFO, buffer[i])
        
        # update length        
        self.writeRegister(REG_PAYLOAD_LENGTH, currentLength + size)
        return size
        

    def parsePacket(self, size = 0):
        packetLength = 0
        irqFlags = self.readRegister(REG_IRQ_FLAGS)

        if size > 0:
            self.implicitHeaderMode()
            self.writeRegister(REG_PAYLOAD_LENGTH, size & 0xff)
        else:
            self.explicitHeaderMode()

        # clear IRQ's
        self.writeRegister(REG_IRQ_FLAGS, irqFlags)

        # if (irqFlags & IRQ_RX_DONE_MASK) and \
           # (irqFlags & IRQ_RX_TIME_OUT_MASK == 0) and \
           # (irqFlags & IRQ_PAYLOAD_CRC_ERROR_MASK == 0):
           
        if (irqFlags == IRQ_RX_DONE_MASK):  # RX_DONE only
            # automatically standby when RX_DONE            
            # received a packet
            self.standby()  # in case not standby automatically            
            self._packetIndex = 0

            # read packet length
            if self._implicitHeaderMode:
                packetLength = self.readRegister(REG_PAYLOAD_LENGTH)
            else:
                packetLength = self.readRegister(REG_RX_NB_BYTES)
            
            FifoRxCurrentAddr = self.readRegister(REG_FIFO_RX_CURRENT_ADDR)                
            self.writeRegister(REG_FIFO_ADDR_PTR, FifoRxCurrentAddr)
               
            self.collect_garbage()
            
        elif self.readRegister(REG_OP_MODE) != (MODE_LONG_RANGE_MODE | MODE_RX_SINGLE):
            # no packet received.            
            # reset FIFO address
            self.writeRegister(REG_FIFO_ADDR_PTR, FifoRxBaseAddr)

            # put in single RX mode
            self.writeRegister(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_RX_SINGLE) 

        return packetLength
        
        
    def available(self): 
        available = self._packetIndex < self.readRegister(REG_RX_NB_BYTES)        
        not_end_of_buffer = self.readRegister(REG_FIFO_ADDR_PTR) < MAX_PKT_LENGTH 
        
        return available and not_end_of_buffer


    def read(self):
        if self.available():
            self._packetIndex += 1
            return self.readRegister(REG_FIFO) 
        
        
    def standby(self):
        self.writeRegister(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_STDBY)

        
    def sleep(self):
        self.writeRegister(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_SLEEP)
        
        
    def setTxPower(self, level, outputPin = PA_OUTPUT_PA_BOOST_PIN):
        if (outputPin == PA_OUTPUT_RFO_PIN):
            # RFO
            if level < 0:
                evel = 0
            elif level > 14:
                level = 14 

            self.writeRegister(REG_PA_CONFIG, 0x70 | level)
            
        else:
            # PA BOOST
            if level < 2:
                level = 2
            elif level > 17:
                level = 17 

            self.writeRegister(REG_PA_CONFIG, PA_BOOST | (level - 2))
            

    def setFrequency(self, frequency):
        self._frequency = frequency    
        
        frfs = {169E6: (42, 64, 0), 
                433E6: (108, 64, 0),
                434E6: (108, 128, 0),
                866E6: (216, 128, 0),
                868E6: (217, 0, 0),
                915E6: (228, 192, 0)}

        self.writeRegister(REG_FRF_MSB, frfs[frequency][0])
        self.writeRegister(REG_FRF_MID, frfs[frequency][1])
        self.writeRegister(REG_FRF_LSB, frfs[frequency][2])
        

    def setSpreadingFactor(self, sf):
        if sf < 6:
            sf = 6
        elif sf > 12:
            sf = 12 

        if sf == 6:
            self.writeRegister(REG_DETECTION_OPTIMIZE, 0xc5)
            self.writeRegister(REG_DETECTION_THRESHOLD, 0x0c)
        else:
            self.writeRegister(REG_DETECTION_OPTIMIZE, 0xc3)
            self.writeRegister(REG_DETECTION_THRESHOLD, 0x0a) 

        self.writeRegister(REG_MODEM_CONFIG_2, (self.readRegister(REG_MODEM_CONFIG_2) & 0x0f) | ((sf << 4) & 0xf0))

        
    def setSignalBandwidth(self, sbw):
        
        bw = 9

        if (sbw <= 7.8E3):
            bw = 0
        elif (sbw <= 10.4E3):
            bw = 1
        elif (sbw <= 15.6E3):
            bw = 2
        elif (sbw <= 20.8E3):
            bw = 3
        elif (sbw <= 31.25E3):
            bw = 4
        elif (sbw <= 41.7E3):
            bw = 5
        elif (sbw <= 62.5E3):
            bw = 6
        elif (sbw <= 125E3):
            bw = 7
        elif (sbw <= 250E3):
            bw = 8
        
        self.writeRegister(REG_MODEM_CONFIG_1, (self.readRegister(REG_MODEM_CONFIG_1) & 0x0f) | (bw << 4))


    def setCodingRate(self, denominator):
        if denominator < 5:
            denominator = 5
        elif denominator > 8:
            denominator = 8

        cr = denominator - 4
        self.writeRegister(REG_MODEM_CONFIG_1, (self.readRegister(REG_MODEM_CONFIG_1) & 0xf1) | (cr << 1))
        

    def setPreambleLength(self, length):
        self.writeRegister(REG_PREAMBLE_MSB,  (length >> 8) & 0xff)
        self.writeRegister(REG_PREAMBLE_LSB,  (length >> 0) & 0xff)
        
        
    def enableCRC(self):
        self.writeRegister(REG_MODEM_CONFIG_2, self.readRegister(REG_MODEM_CONFIG_2) | 0x04)
        

    # def disableCRC(self):
        # self.writeRegister(REG_MODEM_CONFIG_2, self.readRegister(REG_MODEM_CONFIG_2) & 0xfb)
  
 
    # def setSyncWord(self, sw):
        # self.writeRegister(REG_SYNC_WORD, sw) 
         

    # def dumpRegisters(self):
        # for i in range(128):
            # print("0x{0:02x}: {1}".format(i, self.readRegister(i)))
            

    def explicitHeaderMode(self):
        self._implicitHeaderMode = False
        self.writeRegister(REG_MODEM_CONFIG_1, self.readRegister(REG_MODEM_CONFIG_1) & 0xfe)

    
    def implicitHeaderMode(self):
        self._implicitHeaderMode = True
        self.writeRegister(REG_MODEM_CONFIG_1, self.readRegister(REG_MODEM_CONFIG_1) | 0x01)
       
        
    # p0.irq(trigger=Pin.IRQ_FALLING, handler=callback)
    # p2.irq(trigger=Pin.IRQ_RISING | Pin.IRQ_FALLING, handler=callback)
    def onReceive(self, callback):
        self._onReceive = callback

        if callback:
            self.writeRegister(REG_DIO_MAPPING_1, 0x00)
            self._irq.irq(trigger = Pin.IRQ_RISING, handler = self.handleDio0Rise)
        else:
            self._irq.irq(trigger = 0)
        

    def receive(self, size = 0):
        if size > 0:
            self.implicitHeaderMode()
            self.writeRegister(REG_PAYLOAD_LENGTH, size & 0xff)
        else:
            self.explicitHeaderMode() 
        
        self.sleep()  # sleep mode will clear FIFO
        self.writeRegister(REG_OP_MODE, MODE_LONG_RANGE_MODE | MODE_RX_CONTINUOUS) 
                 
                 
    def handleDio0Rise(self, event_source):
        
        irqFlags = self.readRegister(REG_IRQ_FLAGS)

        # clear IRQ's
        self.writeRegister(REG_IRQ_FLAGS, irqFlags)

        if (irqFlags & IRQ_PAYLOAD_CRC_ERROR_MASK) == 0:
            # received a packet
            self._packetIndex = 0

            # read packet length
            packetLength = self.readRegister(REG_PAYLOAD_LENGTH) if self._implicitHeaderMode else self.readRegister(REG_RX_NB_BYTES)

            # set FIFO address to current RX address
            self.writeRegister(REG_FIFO_ADDR_PTR, self.readRegister(REG_FIFO_RX_CURRENT_ADDR))

            if self._onReceive:
                self._onReceive(self, packetLength)

            # reset FIFO address
            self.writeRegister(REG_FIFO_ADDR_PTR, FifoRxBaseAddr) 
            
            self.collect_garbage()

        
    def readRegister(self, address, byteorder = 'big', signed = False):
        response = self.singleTransfer(address & 0x7f)
        return int.from_bytes(response, byteorder, signed)  
        

    def writeRegister(self, address, value):
        self.singleTransfer(address | 0x80, value)


    def singleTransfer(self, address, value = 0x00):        
        response = bytearray(1)
        
        self._ss.value(0)
         
        self._spi.write(bytes([address]))
        self._spi.write_readinto(bytes([value]), response)
        
        self._ss.value(1)

        return response   
        