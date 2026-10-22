# SPDX-License-Identifier: GPL-2.0-or-later
"""Cairo color controls; no hardware access."""
import colorsys
import math
import cairo
import gi

gi.require_version('Gtk', '4.0')
from gi.repository import Gtk, Gdk, GObject


def clamp(value):
    return max(0.0, min(1.0, value))


def rounded(cr, x, y, width, height, radius):
    radius=min(radius,width/2,height/2)
    cr.new_sub_path()
    for cx,cy,start in [(x+width-radius,y+radius,-90),(x+width-radius,y+height-radius,0),
                        (x+radius,y+height-radius,90),(x+radius,y+radius,180)]:
        cr.arc(cx,cy,radius,math.radians(start),math.radians(start+90))
    cr.close_path()


class ColorPlane(Gtk.DrawingArea):
    __gsignals__={'color-changed':(GObject.SignalFlags.RUN_FIRST,None,())}

    def __init__(self, hue_only=False):
        super().__init__()
        self.hue_only=hue_only
        self.h,self.s,self.v=0.5,0.7,1.0
        self.set_content_height(30 if hue_only else 230)
        self.set_hexpand(True); self.set_focusable(True)
        self.set_cursor_from_name('crosshair' if not hue_only else 'pointer')
        self.set_tooltip_text('Hue: left/right arrow keys' if hue_only else 'Saturation and value: arrow keys; Shift for larger steps')
        self.update_property([Gtk.AccessibleProperty.LABEL],['Hue' if hue_only else 'Saturation and value'])
        self.set_draw_func(self.draw)
        drag=Gtk.GestureDrag()
        drag.connect('drag-begin',self.begin)
        drag.connect('drag-update',self.drag)
        self.add_controller(drag)
        keys=Gtk.EventControllerKey(); keys.connect('key-pressed',self.key)
        self.add_controller(keys)

    def set_hsv(self,h,s,v):
        self.h,self.s,self.v=h,s,v; self.queue_draw()

    def begin(self,gesture,x,y):
        self.start=(x,y); self.grab_focus(); self.pick(x,y)

    def drag(self,gesture,x,y):
        self.pick(self.start[0]+x,self.start[1]+y)

    def pick(self,x,y):
        if self.hue_only: self.h=clamp((x-7)/max(1,self.get_width()-14))
        else:
            self.s=clamp((x-7)/max(1,self.get_width()-14))
            self.v=1-clamp((y-7)/max(1,self.get_height()-14))
        self.queue_draw(); self.emit('color-changed')

    def key(self,controller,keyval,keycode,state):
        step=0.05 if state & Gdk.ModifierType.SHIFT_MASK else 0.01
        if keyval not in (Gdk.KEY_Left,Gdk.KEY_Right,Gdk.KEY_Up,Gdk.KEY_Down): return False
        if self.hue_only:
            self.h=clamp(self.h+step*(1 if keyval in (Gdk.KEY_Right,Gdk.KEY_Up) else -1))
        elif keyval in (Gdk.KEY_Left,Gdk.KEY_Right):
            self.s=clamp(self.s+step*(1 if keyval==Gdk.KEY_Right else -1))
        else: self.v=clamp(self.v+step*(1 if keyval==Gdk.KEY_Up else -1))
        self.queue_draw(); self.emit('color-changed'); return True

    def draw(self,widget,cr,w,h):
        x,y,ww,hh=7,7,w-14,h-14
        cr.save(); rounded(cr,x,y,ww,hh,hh/2 if self.hue_only else 12); cr.clip()
        if self.hue_only:
            grad=cairo.LinearGradient(x,0,x+ww,0)
            for i in range(7): grad.add_color_stop_rgb(i/6,*colorsys.hsv_to_rgb(i/6,1,1))
            cr.set_source(grad); cr.paint()
            cx,cy=x+self.h*ww,h/2
        else:
            cr.set_source_rgb(*colorsys.hsv_to_rgb(self.h,1,1)); cr.paint()
            grad=cairo.LinearGradient(x,0,x+ww,0)
            grad.add_color_stop_rgba(0,1,1,1,1); grad.add_color_stop_rgba(1,1,1,1,0)
            cr.set_source(grad); cr.paint()
            grad=cairo.LinearGradient(0,y,0,y+hh)
            grad.add_color_stop_rgba(0,0,0,0,0); grad.add_color_stop_rgba(1,0,0,0,1)
            cr.set_source(grad); cr.paint()
            cx,cy=x+self.s*ww,y+(1-self.v)*hh
        cr.restore()
        cr.arc(cx,cy,7,0,2*math.pi); cr.set_source_rgba(0,0,0,0.6); cr.set_line_width(5); cr.stroke()
        cr.arc(cx,cy,7,0,2*math.pi); cr.set_source_rgb(1,1,1); cr.set_line_width(2.5); cr.stroke()
        if self.has_focus():
            rounded(cr,1,1,w-2,h-2,14); cr.set_source_rgba(0.7,0.85,1,0.9); cr.set_line_width(2); cr.stroke()

