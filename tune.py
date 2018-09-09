# I. Kantorski, 2017

import numpy as np
import pyaudio

import threading, time
from Queue import Queue


nFFT = 2048
BUF_SIZE = 4 * nFFT
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 11000

OUTRATE = 44100         #Cz. probkowania DAC
OUT_WIDTH_IN_BYTES = 2  #rozdzielczosc przetwornika DAC
CHUNK = 44100 / 10

def parseInput(text):
    if text == "e" or text == "1":
        given_f = 329.63
        isNote = True
        terminate = False
    elif text == "B" or text == "h" or text == "2":
        given_f = 246.94
        isNote = True
        terminate = False
    elif text == "G" or text == "3":
        given_f = 196.00
        isNote = True
        terminate = False
    elif text == "D" or text == "4":
        given_f = 146.83
        isNote = True
        terminate = False
    elif text == "A" or text == "5":
        given_f = 110.00
        isNote = True
        terminate = False
    elif text == "E" or text == "6":
        given_f = 82.41
        isNote = True
        terminate = False
    elif text.endswith("Hz") or text.endswith("HZ") or text.endswith("hz"):
        try:
            given_f = float(text[0:-2].replace(',','.'))
            isNote = True
            terminate = False
        except:
            given_f = 110.0
            isNote = False
            terminate = False
    elif text == "S" or text == "s":
        given_f = 110.0
        isNote = False
        terminate = True
    else:
        given_f = 110.0
        isNote = False
        terminate = False

    return given_f, isNote, terminate


def process_spectra(A_spec, F_spec, SetPoint):
    l_filter = F_spec > 60
    F_new_spec = F_spec
    A_new_spec = A_spec * l_filter
    th = 50
    A_new_spec = A_new_spec * (A_new_spec > th)
    max_f_arg = np.argmax(A_new_spec)
    max_f = F_new_spec[max_f_arg]

    #rozwazmy trzy kolejne harmoniczne
    #0 harmonic:
    delta_0 = max_f -   SetPoint
    #1 harmonic:
    delta_1 = max_f - 2*SetPoint
    #2 harmonic:
    delta_2 = max_f - 3*SetPoint
    d_tab = np.array([delta_0, delta_1, delta_2])
    #wybierz najblizsza harmoniczna:
    delta_min = d_tab[np.argmin([abs(delta_0), abs(delta_1), abs(delta_2)])]

    return delta_min, max_f

def translate_f(delta):

    #absolute mean higer, lower or ok
    if delta > 1:
        out_abs = 700
    elif delta < -1:
        out_abs = 200
    else:
        out_abs = 440
    #relative means how much higher or lower
    if abs(delta) < 1:
        out_rel = 0
    elif abs(delta) < 40:
        out_rel =(25.0/39)*(delta-1)
    else:
        out_rel = 25

    return out_abs, out_rel

def ack(p, stream, out_q):
    if not kill:
        N = max(stream.get_read_available() / nFFT, 1) * nFFT
        data = stream.read(N)
        y = 1.0 * np.fromstring(data, np.int16) / MAX_y


        Y_raw = np.abs(np.fft.fft(y))
        Y_L = Y_raw[0:len(Y_raw)/2]

        freq_raw = np.fft.fftfreq(y.size, d = 1.0 / RATE )
        freq = freq_raw[0:len(freq_raw)/2]

        delta, f = process_spectra(Y_L, freq, Note_f) #B
        out_abs, out_rel = translate_f(delta)

        out_q.put((out_abs, out_rel)) #que = (data1, data2)

    return 0

def play(stream, nbytes, in_q, stop = False ):

    #once - give signal that program is ready
    firstSine = np.sin(np.linspace(0, 440*2*np.pi, num=OUTRATE, endpoint = False))*10000
    strFirstSine = firstSine.astype('int'+str(nbytes*8)).tobytes()
    stream.write(strFirstSine)


    #initialize vars
    lastEndPhase = 0
    lastEndPhaseMod = 0
    f = 440
    fmod = 0
    while not kill:
        try:
            ack_que = in_q.get(block = False)
            f = ack_que[0]
            fmod = ack_que[1]
        except:
            pass

        #generate base tone
        currStartPhase = lastEndPhase % (2*np.pi)
        currEndPhase = (lastEndPhase % (2*np.pi)) + f*2*np.pi*CHUNK/OUTRATE
        basicSine = np.sin(np.linspace(currStartPhase, currEndPhase, num=CHUNK, endpoint = False))
        lastEndPhase = currEndPhase

        #generate low frequency amplitude modulator
        currStartPhaseMod = lastEndPhaseMod % (2*np.pi)
        currEndPhaseMod = (lastEndPhaseMod % (2*np.pi)) + fmod*2*np.pi*CHUNK/OUTRATE
        phaseMod = np.linspace(currStartPhaseMod, currEndPhaseMod, num=CHUNK, endpoint = False)
        modSine = np.cos(phaseMod)
        lastEndPhaseMod = currEndPhaseMod

        #Modulate the amplitude
        dataWindow = ((basicSine*(modSine+1.2)*0.5)*10000)
        #convert to string bytes
        strDataWindow = dataWindow.astype('int'+str(nbytes*8)).tobytes()

        if not do_not_play:
            stream.write(strDataWindow)
        else:
            time.sleep(1.0*CHUNK/OUTRATE)
    return 0

def cyclic(interval = 1, fcn = lambda: 1, args = (None,)):
    next_call = time.time()                 #t0
    while not kill:
        #last = time.time()
        fcn(*args)                          #t0 + t_instr
        #last = time.time() - last
        next_call = next_call + interval;   #t0 + 1s
        time.sleep(next_call - time.time()) #t0 + 1s - (t0 + 1t_instr)
    return 0




##Setup Puaudio instance
pin = pyaudio.PyAudio()
MAX_y = 2.0 ** (pin.get_sample_size(FORMAT) * 8 - 1)
Y = np.zeros(nFFT)

#open input stream from mic
stream_in = pin.open(format=FORMAT,
                channels=CHANNELS,
                rate=RATE,
                input=True,
                frames_per_buffer=BUF_SIZE)

#open output stream to speakers/headphones
stream_out = pin.open(  format = pin.get_format_from_width(OUT_WIDTH_IN_BYTES),
                        channels = 1,
                        rate = OUTRATE,
                        output = True)

#Queue for ordered thread communication
que = Queue()

do_not_play = True
kill = False
Note_f = 110.0

timerThreadIn = threading.Thread(target=cyclic, args = (0.8, ack, (pin, stream_in, que)))
timerThreadIn.daemon = True
timerThreadIn.start()

timerThreadOut = threading.Thread(target=play, args = (stream_out, OUT_WIDTH_IN_BYTES, que))
timerThreadOut.deamon = True
timerThreadOut.start()


keyb_input = "p"
while keyb_input != "S":
    keyb_input = raw_input("Podaj Strune: ")
    Note_f, isNote, terminate = parseInput(keyb_input)
    do_not_play = not isNote
    if terminate:
        keyb_input = "S"
        kill = True


kill = True
time.sleep(2)

stream_in.stop_stream()
stream_in.close()

stream_out.stop_stream()
stream_out.close()

pin.terminate()
