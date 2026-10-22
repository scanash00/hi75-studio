import json, math
from pathlib import Path
from gi.repository import Gtk, GObject
LAYOUT=json.loads(Path(__file__).with_name('keyboard-layout.json').read_text())
def rounded(c,x,y,w,h,r,color):
    c.new_sub_path()
    for a,b,start in ((x+w-r,y+r,-90),(x+w-r,y+h-r,0),(x+r,y+h-r,90),(x+r,y+r,180)):
        c.arc(a,b,r,math.radians(start),math.radians(start+90))
    c.close_path(); c.set_source_rgb(*(v/255 for v in color)); c.fill()
class Keyboard(Gtk.DrawingArea):
    __gsignals__={"key-selected":(GObject.SignalFlags.RUN_FIRST,None,(int,))}
    def __init__(self):
        super().__init__(); self.set_content_height(280); self.set_hexpand(True); self.set_draw_func(self.draw)
        self.selected=None; self.interactive=False; self.hitboxes=[]
        click=Gtk.GestureClick(); click.connect("released",self.clicked); self.add_controller(click)
        self.set_tooltip_text('HI75 · 75% layout with rotary knob')
    def clicked(self,gesture,count,x,y):
        if self.interactive:
            for pos,left,top,w,h in self.hitboxes:
                if left<=x<=left+w and top<=y<=top+h:
                    self.emit("key-selected",pos); return
    def draw(self,area,c,width,height):
        unit=min((width-32)/16.5,(height-20)/6.5); w=unit*16.5+20; h=unit*6.5+16
        dx,dy=(width-w)/2,(height-h)/2
        c.translate(dx,dy); self.hitboxes=[]
        rounded(c,0,5,w,h,12,(30,28,27)); rounded(c,0,2,w,h-3,12,(198,201,204)); rounded(c,0,0,w,h-6,12,(238,240,241))
        brown={0,6,7,8,9,28,58,80,73,87,88,89}; taupe={29,30,44,45,59,60,71,74,75,76,77,83,84,85}
        for pos,x,y,kw,label in LAYOUT:
            x=x*unit+12; y=y*unit+8; a=kw*unit-4; b=unit-4
            self.hitboxes.append((pos,x+dx,y+dy,a,b))
            if self.selected==pos: rounded(c,x-3,y-3,a+6,b+8,5,(214,151,90))
            if pos==14:
                c.arc(x+a/2,y+b/2,min(a,b)/2,0,math.tau); c.set_source_rgb(.35,.35,.34); c.fill()
                c.arc(x+a/2,y+b/2,min(a,b)/2-3,0,math.tau); c.set_source_rgb(.85,.85,.82); c.fill(); continue
            top,edge,ink=((91,64,56),(60,43,38),(244,242,226)) if pos in brown else (((190,180,157),(143,135,116),(69,53,44)) if pos in taupe else ((244,242,226),(188,189,174),(69,53,44)))
            rounded(c,x,y+2,a,b,3,edge); rounded(c,x+1,y,a-2,b-2,3,top)
            c.set_source_rgb(*(v/255 for v in ink)); c.select_font_face('Sans'); c.set_font_size(max(6,min(11,unit*.23)))
            if label in ('Left','Right','Up','Down'):
                c.save(); c.translate(x+a/2,y+b/2); c.rotate({'Right':0,'Down':math.pi/2,'Left':math.pi,'Up':-math.pi/2}[label]); d=max(2,unit*.1)
                c.set_line_width(1); c.move_to(-d,0); c.line_to(d,0); c.move_to(0,-d); c.line_to(d,0); c.line_to(0,d); c.stroke(); c.restore(); continue
            if label=='Space': label=''
            ext=c.text_extents(label); c.move_to(x+(a-ext.width)/2-ext.x_bearing,y+(b-ext.height)/2-ext.y_bearing-1); c.show_text(label)
