#!/usr/bin/python
# -*- coding: utf-8 -*-

import gtk, gobject, datetime, pango, socket, signal, sys, dbus
from time import time, localtime, strftime
from threading import Thread

def formatNetUsage(bytes):
    kilos = float(bytes.replace(",", ".")) / 1024
    if kilos < 1024:
        return str(round(kilos, 2)) + "Kt/s"
    return str(round(kilos / 1024, 2)) + "Mt/s"

def humanizeSize(size):
    units = ["t", "K", "M", "G", "T", "P", "E"]
    i = 0
    size = long(size)
    while size > 1024:
        size /= 1024
        i += 1
    return str(int(round(size))) + units[i]

def timeToSecs(time):
    units = time.split(":")
    i = 0
    secs = 0
    for unit in reversed(units):
        secs += pow(60, i) * int(unit)
        i += 1
    return secs


class Graph(object):
    def __init__(self):
        self.pixbuf = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False, 8, 400, 200)
        self.pixmap, self.mask = self.pixbuf.render_pixmap_and_mask()

        self.cm = self.pixmap.get_colormap()
        
        self.image = gtk.Image()
        self.image.set_from_pixmap(self.pixmap, self.mask)
    
    def getImage(self):
        return self.image

class CpuGraph(Graph):
    def __init__(self):
        super(CpuGraph, self).__init__()
        
        self.usageDict = dict()
        
        self.gcBlack = self.pixmap.new_gc(foreground=self.cm.alloc_color('black'))
        self.gcColors = []
        self.gcColors.append(self.pixmap.new_gc(foreground=self.cm.alloc_color('#ff0000')))
        self.gcColors.append(self.pixmap.new_gc(foreground=self.cm.alloc_color('#00ff00')))
        self.gcColors.append(self.pixmap.new_gc(foreground=self.cm.alloc_color('#0000ff')))
        self.gcColors.append(self.pixmap.new_gc(foreground=self.cm.alloc_color('#ffff00')))
        self.gcColors.append(self.pixmap.new_gc(foreground=self.cm.alloc_color('#0000ff')))
        self.gcColors.append(self.pixmap.new_gc(foreground=self.cm.alloc_color('#ff00ff')))
        self.gcColors.append(self.pixmap.new_gc(foreground=self.cm.alloc_color('#C0C0C0'))) # silver
        self.gcColors.append(self.pixmap.new_gc(foreground=self.cm.alloc_color('#808000'))) # olive
        self.gcColors.append(self.pixmap.new_gc(foreground=self.cm.alloc_color('#800080'))) # purple
        self.gcColors.append(self.pixmap.new_gc(foreground=self.cm.alloc_color('#800000'))) # maroon
        self.gcColors.append(self.pixmap.new_gc(foreground=self.cm.alloc_color('#008080'))) # teal
        self.gcColors.append(self.pixmap.new_gc(foreground=self.cm.alloc_color('#008000'))) # green
    
    def add(self, core, usage):
        if core not in self.usageDict:
            self.usageDict[core] = []
        usage = int(usage)*2
        if usage == 200:
            usage = 199
        self.usageDict[core].insert(0, usage)
        if len(self.usageDict[core]) > 200:
            self.usageDict[core] = self.usageDict[core][:200]
    
    def drawGraph(self):
        self.pixmap.draw_rectangle(self.gcBlack, True, 0, 0, 400, 200)
        interval = 5
        colorNum = 0
        for core in self.usageDict.itervalues():
            if len(core) < 2:
                continue
            points = []
            i = 0
            for usage in core:
                points.append((399-i*interval, 199-usage))
                i += 1
                if i*interval > 400:
                    break
            self.pixmap.draw_lines(self.gcColors[colorNum], points)
            colorNum += 1
        self.image.set_from_pixmap(self.pixmap, self.mask)

class NetGraph(Graph):
    def __init__(self):
        super(NetGraph, self).__init__()
        
        self.downList = []
        self.upList = []
        
        self.gcGreen = self.pixmap.new_gc(foreground=self.cm.alloc_color('green'))
        self.gcBlue = self.pixmap.new_gc(foreground=self.cm.alloc_color('blue'))
        self.gcMagenta = self.pixmap.new_gc(foreground=self.cm.alloc_color('magenta'))
        self.gcBlack = self.pixmap.new_gc(foreground=self.cm.alloc_color('black'))
    
    def addDown(self, data):
        self.downList.insert(0, int(round(float(data.replace(",", ".")) / 1024)))
        if len(self.downList) > 400:
            self.downList = self.downList[:400]
    
    def addUp(self, data):
        self.upList.insert(0, int(round(float(data.replace(",", ".")) / 1024)))
        if len(self.upList) > 400:
            self.upList = self.upList[:400]
    
    def drawGraph(self):
        maxVal = max(max(self.downList), max(self.upList))
        if maxVal <= 200:
            self.__drawGraph(self.downList, self.upList)
            return
        divider = maxVal / 200
        normalizedDownList = []
        normalizedUpList = []
        for i in range(min(len(self.downList), len(self.upList))):
            normalizedDownList.append(int(self.downList[i] / divider))
            normalizedUpList.append(int(self.upList[i] / divider))
        self.__drawGraph(normalizedDownList, normalizedUpList)
    
    def __drawGraph(self, downList, upList):
        self.pixmap.draw_rectangle(self.gcBlack, True, 0, 0, 400, 200)
        for i in range(min(400, len(downList), len(upList))):
            common = min(downList[i], upList[i])
            if common > 0:
                self.pixmap.draw_line(self.gcMagenta, 399-i, 199, 399-i, 200-common)
            if downList[i] > common:
                self.pixmap.draw_line(self.gcGreen, 399-i, 200-common, 399-i, 200-downList[i])
            elif upList[i] > common:
                self.pixmap.draw_line(self.gcBlue, 399-i, 200-common, 399-i, 200-upList[i])
        self.image.set_from_pixmap(self.pixmap, self.mask)

class DriveInfo(object):
    def __init__(self):
        self.driveDict = dict()
        self.needsUpdate = True
        
        self.label = gtk.Label()
        self.label.modify_font(pango.FontDescription("14"))
        self.label.set_justify(gtk.JUSTIFY_LEFT)
    
    def getLabel(self):
        return self.label
    
    def add(self, drive, spaceLeft):
        key = drive[:2]
        spaceLeft = humanizeSize(spaceLeft)
        if key not in self.driveDict or self.driveDict[key] != spaceLeft:
            self.driveDict[key] = spaceLeft
            self.needsUpdate = True
    
    def update(self):
        if not self.needsUpdate:
            return
        usageStr = ""
        for drive in sorted(self.driveDict.iterkeys()):
            usageStr += ("" if len(usageStr) == 0 else "   ") + drive + " " + self.driveDict[drive]
        self.label.set_text(usageStr)
        self.needsUpdate = False

class NowPlaying(object):
    def __init__(self):
        self.trackLabel = gtk.Label()
        self.trackLabel.modify_font(pango.FontDescription("18"))
        self.trackLabel.set_size_request(800,-1)
        self.trackLabel.set_justify(gtk.JUSTIFY_CENTER)
        self.trackLabel.set_line_wrap(True)
        self.trackLabel.set_line_wrap_mode(pango.WRAP_WORD_CHAR)

        self.trackSpacer = gtk.VBox(False, 0)
        
        self.statusLabel = gtk.Label()
        self.statusLabel.modify_font(pango.FontDescription("monospace 14"))
        self.statusLabel.set_justify(gtk.JUSTIFY_CENTER)
        
        self.pixbuf = gtk.gdk.Pixbuf(gtk.gdk.COLORSPACE_RGB, False, 8, 800, 20)
        self.pixmap, self.mask = self.pixbuf.render_pixmap_and_mask()
        self.cm = self.pixmap.get_colormap()
        self.image = gtk.Image()
        self.image.set_from_pixmap(self.pixmap, self.mask)
        self.gcBlack = self.pixmap.new_gc(foreground=self.cm.alloc_color('black'))
        self.gcGreen = self.pixmap.new_gc(foreground=self.cm.alloc_color('green'))
    
    def getTrackLabel(self):
        return self.trackLabel
    
    def getStatusLabel(self):
        return self.statusLabel
    
    def getPositionImage(self):
        return self.image
    
    def getTrackSpacer(self):
        return self.trackSpacer

    def centerTrackLabel(self):
        layout = self.trackLabel.get_layout()
        width, height = layout.get_pixel_size()
        self.trackSpacer.set_size_request((800 - width)/2, -1)

    def updateNp(self, data):
        if len(data) == 0 or data.count(" -+- ") != 4:
            self.trackLabel.set_text("")
            self.statusLabel.set_text("")
            self.pixmap.draw_rectangle(self.gcBlack, True, 0, 0, 800, 20)
            self.image.set_from_pixmap(self.pixmap, self.mask)
            return
        artist, track, paused, position, length = data.split(" -+- ")
        self.trackLabel.set_size_request(800,-1)
        self.trackLabel.set_text(artist + "\n" + track)
        self.centerTrackLabel()
        self.statusLabel.set_text(("Paused" if paused == "1" else "Playing") + " @ " + position + "/" + length)
        
        self.pixmap.draw_rectangle(self.gcBlack, True, 0, 0, 800, 20)
        if length != "?":
            self.pixmap.draw_rectangle(self.gcGreen, True, 0, 0, int(round(800 * (1.0*timeToSecs(position)/timeToSecs(length)))), 20)
        self.image.set_from_pixmap(self.pixmap, self.mask)

class Base:
    def __init__(self):
        gobject.threads_init()
        
        self.fontMonospace = pango.FontDescription("monospace 14")
        self.fontNormal = pango.FontDescription("14")
        
        self.lastInputTime = time()
        self.continueListening = True
        self.displayOn = True
        
        window = gtk.Window(gtk.WINDOW_TOPLEVEL)
        window.fullscreen()
        window.connect("destroy", gtk.main_quit)

        vbox = gtk.VBox(False, 0)
        hboxTop = gtk.HBox(False, 0)

        self.clockLabel = gtk.Label()
        self.clockLabel.modify_font(self.fontMonospace)
        hboxTop.pack_start(self.clockLabel, False, False, 0)

        self.timeSinceLastInputLabel = gtk.Label()
        self.timeSinceLastInputLabel.modify_font(self.fontMonospace)
        hboxTop.pack_start(self.timeSinceLastInputLabel, True, True, 0)
        
        self.renderTimeLabel = gtk.Label()
        self.renderTimeLabel.modify_font(self.fontMonospace)
        hboxTop.pack_end(self.renderTimeLabel, False, False, 0)
        vbox.pack_start(hboxTop, False, False, 0)

        hboxCpuNet = gtk.HBox(False, 0)
        self.cpuGraph = CpuGraph()
        hboxCpuNet.pack_start(self.cpuGraph.getImage(), False, False, 0)
        self.netGraph = NetGraph()
        hboxCpuNet.pack_start(self.netGraph.getImage(), False, False, 0)
        vbox.pack_start(hboxCpuNet, False, False, 0)
        
        
        hbox3 = gtk.HBox(True, 0)
        self.cpuLabel = gtk.Label("CPU: ")
        self.cpuLabel.modify_font(self.fontMonospace)
        self.cpuLabel.set_alignment(0, 0)
        hbox3.pack_start(self.cpuLabel, True, True, 0)
        
        self.memLabel = gtk.Label("MEM: ")
        self.memLabel.modify_font(self.fontMonospace)
        self.memLabel.set_alignment(0, 0)
        hbox3.pack_start(self.memLabel, True, True, 0)
        
        self.netDownLabel = gtk.Label("Down: ")
        self.netDownLabel.modify_font(self.fontMonospace)
        self.netDownLabel.set_alignment(0, 0)
        hbox3.pack_start(self.netDownLabel, True, True, 0)
        
        self.netUpLabel = gtk.Label("Up: ")
        self.netUpLabel.modify_font(self.fontMonospace)
        self.netUpLabel.set_alignment(0, 0)
        hbox3.pack_end(self.netUpLabel, True, True, 0)
        vbox.pack_start(hbox3, False, False, 0)
        
        
        hbox4 = gtk.HBox(True, 0)
        self.volLabel = gtk.Label("Vol: ")
        self.volLabel.modify_font(self.fontMonospace)
        self.volLabel.set_alignment(0, 0)
        self.volLabel.set_use_markup(True)
        hbox4.pack_start(self.volLabel, True, True, 0)
        
        self.totLabel = gtk.Label("Tot: ")
        self.totLabel.modify_font(self.fontMonospace)
        self.totLabel.set_alignment(0, 0)
        hbox4.pack_start(self.totLabel, True, True, 0)
        
        self.localIpLabel = gtk.Label()
        self.localIpLabel.modify_font(self.fontMonospace)
        self.localIpLabel.set_alignment(0, 0)
        hbox4.pack_start(self.localIpLabel, True, True, 0)
        
        self.remoteIpLabel = gtk.Label()
        self.remoteIpLabel.modify_font(self.fontMonospace)
        self.remoteIpLabel.set_alignment(0, 0)
        hbox4.pack_end(self.remoteIpLabel, True, True, 0)
        vbox.pack_start(hbox4, False, False, 0)
        
        
        self.driveInfo = DriveInfo()
        vbox.pack_start(self.driveInfo.getLabel(), False, False, 0)
        
        
        vboxNp = gtk.VBox(False, 0)
        self.np = NowPlaying()
        hboxTrack = gtk.HBox(False, 0)
        hboxTrack.pack_start(self.np.getTrackSpacer(), False, False, 0)
        hboxTrack.pack_end(self.np.getTrackLabel(), True, True, 0)
        vboxNp.pack_start(hboxTrack, False, False, 0)
        vboxNp.pack_start(self.np.getStatusLabel(), False, False, 0)
        vboxNp.pack_end(self.np.getPositionImage(), False, False, 0)
        vbox.pack_end(vboxNp, False, False, 0)
        
        
        window.add(vbox)
        window.show_all()
        gobject.timeout_add_seconds(1, self.clockCallback)
        self.clockCallback()
        
        self.dataListenThread = Thread(target=self.dataListen)
        self.dataListenThread.daemon = True
        self.dataListenThread.start()
        
        self.actionListenThread = Thread(target=self.actionListen)
        self.actionListenThread.daemon = True
        self.actionListenThread.start()
        
        signal.signal(signal.SIGINT, self.sigintHandler)
    
    def clockCallback(self):
        self.clockLabel.set_text(strftime("%H:%M:%S %a %d.%m.%y", localtime()))
        timeSinceLastInput = time() - self.lastInputTime
        if timeSinceLastInput > 3:
            self.timeSinceLastInputLabel.set_text(str(datetime.timedelta(seconds=int(timeSinceLastInput))) + " since last input")
        else:
            self.timeSinceLastInputLabel.set_text("")
        return True

    def actionListen(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("", 25462))
        sock.settimeout(3)
        while self.continueListening:
            try:
                data = sock.recv(1024)
                self.handleAction(data)
            except socket.error:
                pass
        sock.close()
    
    def handleAction(self, data):
        command, data = data.split("|")
        if command == "BacklightToggle":
            self.backlightToggle()
        if command == "Quit":
            sys.exit(0)
    
    def backlightToggle(self):
        bus = dbus.SystemBus()
        tklock = bus.get_object('com.nokia.mce','/com/nokia/mce/request')
        if self.displayOn:
            tklock.req_tklock_mode_change(dbus.String("locked"))
        else:
            tklock.req_tklock_mode_change(dbus.String("unlocked"))
        self.displayOn = not self.displayOn
    
    def dataListen(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.bind(("", 25461))
        sock.settimeout(3)
        while self.continueListening:
            try:
                data = sock.recv(4096)
                self.lastInputTime = time()
                gobject.idle_add(self.handleData, data)
            except socket.error:
                pass
        sock.close()
    
    def handleData(self, data):
        try:
            startTime = time()
            if not data.startswith(".start."):
                return
            data = data[7:]
            vol = None
            mute = None
            for line in data.split("\n"):
                parts = line.split("|")
                if len(parts) > 3 or len(parts) < 2:
                    continue
                if parts[0] == "_Total":
                    self.cpuLabel.set_text("CPU: " + parts[1] + "%")
                elif parts[0] == "MemUsed":
                    self.memLabel.set_text("Mem: " + parts[1] + "Mt")
                elif parts[0] == "MemTotal":
                    self.totLabel.set_text("Tot: " + parts[1] + "Mt")
                elif parts[0] == "vol":
                    vol = parts[1]
                elif parts[0] == "LocalIp":
                    self.localIpLabel.set_text(parts[1])
                elif parts[0] == "RemoteIp":
                    self.remoteIpLabel.set_text(parts[1])
                elif parts[0] == "NetIn":
                    self.netDownLabel.set_text("Down: " + formatNetUsage(parts[1]))
                    self.netGraph.addDown(parts[1])
                elif parts[0] == "NetOut":
                    self.netUpLabel.set_text("Up: " + formatNetUsage(parts[1]))
                    self.netGraph.addUp(parts[1])
                elif parts[0] == "DriveInfo":
                    self.driveInfo.add(parts[1], parts[2])
                elif parts[0] == "Np":
                    self.np.updateNp(parts[1])
                elif parts[0] == "mute":
                    mute = parts[1] == "1"
                else:
                    try:
                        core = int(parts[0])
                        self.cpuGraph.add(core, parts[1])
                    except:
                        pass
            if mute:
                self.volLabel.set_markup("<s>Vol: " + vol + "%</s>")
            else:
                self.volLabel.set_text("Vol: " + vol + "%")
            self.netGraph.drawGraph()
            self.cpuGraph.drawGraph()
            self.driveInfo.update()
            self.renderTimeLabel.set_text(str(round((time() - startTime)*1000, 1)) + "ms")
        except:
            print "Failed to parse data: ", sys.exc_info()
            
    
    def sigintHandler(self, signal, frame):
        print "\nClosing..."
        self.continueListening = False
        sys.exit(0)

    def main(self):
        gtk.main()

if __name__ == "__main__":
    base = Base()
    base.main()

