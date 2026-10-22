"""Stock V5 key records and conservative, copy-on-write macro storage."""
import hashlib,json
from pathlib import Path

KEYS={**{chr(65+i):4+i for i in range(26)},**{str(i):29+i for i in range(1,10)},'0':39,
 'Enter':40,'Esc':41,'Backspace':42,'Tab':43,'Space':44,'-':45,'=':46,'[':47,']':48,'\\':49,
 ';':51,"'":52,'`':53,',':54,'.':55,'/':56,'Caps Lock':57,
 **{f'F{i}':57+i for i in range(1,13)},'Print Screen':70,'Scroll Lock':71,'Pause':72,
 'Insert':73,'Home':74,'Page Up':75,'Delete':76,'End':77,'Page Down':78,'Right':79,'Left':80,'Down':81,'Up':82,
 **{f'F{i}':91+i for i in range(13,25)}}
MODIFIERS=['Ctrl','Shift','Alt','Super','Right Ctrl','Right Shift','Right Alt','Right Super']
MEDIA={'Play / pause':0xcd,'Next track':0xb5,'Previous track':0xb6,'Stop playback':0xb7,'Mute':0xe2,'Volume up':0xe9,'Volume down':0xea}
REVERSE={v:k for k,v in KEYS.items()}
PROTECTED={59,84} # Fn and knob press; rotation is not a key record.
# Physical logical positions established from KB.ini, cross-checked with stock records.
POSITIONS={0,12,18,24,30,36,42,48,54,60,66,72,78,84,1,7,13,19,25,31,37,43,49,55,61,67,73,79,85,2,8,14,20,26,32,38,44,50,56,62,68,74,80,86,3,9,15,21,27,33,39,45,51,57,63,69,81,87,4,10,16,22,28,34,40,46,52,58,64,70,82,88,5,11,17,35,53,59,65,77,83,89}
def digest(data): return hashlib.sha256(data).hexdigest()
def integer(value,lo,hi,name):
    if type(value) is not int or not lo<=value<=hi: raise ValueError('Invalid '+name)
    return value

def action_record(action,macros):
    kind=action.get('kind')
    if kind=='keyboard':
        usage=integer(action.get('usage'),0,255,'key')
        if usage and usage not in REVERSE: raise ValueError('Unsupported key')
        mods=integer(action.get('modifiers',0),0,255,'modifiers')
        if not usage and not mods: raise ValueError('Choose a key or modifier')
        return bytes([0,mods,0,usage])
    if kind=='media':
        usage=action.get('usage')
        if type(usage) is not int or usage not in MEDIA.values(): raise ValueError('Unsupported media action')
        return bytes([2,0,usage>>8,usage&255])
    if kind=='macro':
        index=integer(action.get('index'),0,255,'macro')
        if index not in macros: raise ValueError('That macro is no longer on the keyboard')
        return bytes([3,1,1,index]) # Play once, balanced events.
    if kind=='inherit': return bytes(4)
    raise ValueError('Unsupported action')

def describe(record,macros=None):
    t,m,b,a=record
    if not any(record): return 'Use main key'
    if t==0:
        parts=[name for i,name in enumerate(MODIFIERS) if m&(1<<i)]
        parts += [REVERSE.get(v,f'Key {v}') for v in (b,a) if v]
        return ' + '.join(parts)
    if t==2: return next((n for n,v in MEDIA.items() if v==a+(b<<8)),f'Media {a+(b<<8)}')
    if t==3: return (macros or {}).get(a,{}).get('name',f'Macro {a+1}')
    if t==13: return 'Fn'
    if t==7 and a==29: return 'Knob mode / mute'
    return 'Keyboard function'

def patch_key(page,baseline,position,action,macros,bank):
    if len(page)!=512 or digest(page)!=baseline: raise ValueError('Key assignments changed. Reading them again; please retry.')
    if type(position) is not int or position not in POSITIONS or position in PROTECTED: raise ValueError('This key is protected')
    if bank not in (0,2): raise ValueError('Unsupported keymap')
    if action.get('kind')=='inherit' and bank!=2: raise ValueError('Only Fn shortcuts can inherit')
    if action.get('kind')=='original':
        defaults=json.loads(Path(__file__).with_name('keymap-layout.json').read_text())
        item=next(k for k in defaults if k['position']==position)
        record=bytes.fromhex(item['default' if bank==0 else 'fn_default'])
    else:record=action_record(action,macros)
    result=bytearray(page); result[position*4:position*4+4]=record
    return bytes(result)

def parse_macros(data):
    if len(data)!=4096: raise ValueError('Invalid macro storage')
    result={}; spans=[]
    for index in range(256):
        d=data[index*4:index*4+4]; offset=int.from_bytes(d[:2],'little'); length=int.from_bytes(d[2:],'little')
        if not offset and not length: continue
        if offset<1024 or length<1 or offset+length>4096: raise ValueError('Existing macro layout is not supported; it has been preserved')
        prefix=data[offset]; start=offset+1+prefix
        if start>offset+length or (offset+length-start)%4: raise ValueError('Invalid macro event boundaries')
        if any(offset<end and offset+length>begin for begin,end in spans): raise ValueError('Overlapping macro storage')
        spans.append((offset,offset+length))
        name=data[offset+1:start].decode('utf-8',errors='replace') or f'Macro {index+1}'
        events=[list(data[a:a+4]) for a in range(start,offset+length,4)]
        result[index]={'name':name,'offset':offset,'length':length,'events':events}
    return result

def encode_macro(name,steps):
    if not isinstance(name,str) or not name.strip() or len(name.encode('utf-8'))>80: raise ValueError('Use a macro name of 1–80 bytes')
    if not isinstance(steps,list) or not 1<=len(steps)<=64: raise ValueError('Add 1–64 keystrokes')
    events=[]
    for step in steps:
        usage=integer(step.get('usage'),0,255,'key')
        if usage not in REVERSE: raise ValueError('Choose a key for every step')
        mods=integer(step.get('modifiers',0),0,255,'modifiers')
        delay=integer(step.get('delay'),1,32767,'delay')
        for i in range(8):
            if mods&(1<<i): events.append([0x10,0,1,i])
        key_delay=1 if mods else delay
        events.extend([[0,0,20,usage],[0x80,key_delay>>8,key_delay&255,usage]])
        releases=[i for i in reversed(range(8)) if mods&(1<<i)]
        for n,i in enumerate(releases):
            pause=delay if n==len(releases)-1 else 1
            events.append([0x90,pause>>8,pause&255,i])
    label=name.strip().encode('utf-8'); payload=bytes([len(label)])+label+b''.join(bytes(e) for e in events)
    return payload

def decode_steps(events):
    # Only edit the balanced keystroke format this app writes. Preserve other macros.
    steps=[]; i=0
    while i<len(events):
        mods=0; indices=[]
        while i<len(events) and events[i][0]==0x10:
            f,h,l,v=events[i]
            if h or l!=1 or v>7 or mods&(1<<v): return None
            mods|=1<<v; indices.append(v); i+=1
        if i+1>=len(events): return None
        press,release=events[i:i+2]
        if press[0:3]!=[0,0,20] or press[3] not in REVERSE or release[0]!=0x80 or release[3]!=press[3]: return None
        delay=release[1]*256+release[2]
        if not 1<=delay<=32767: return None
        i+=2
        if indices and delay!=1:return None
        releases=list(reversed(indices))
        for n,v in enumerate(releases):
            if i>=len(events) or events[i][0]!=0x90 or events[i][3]!=v:return None
            pause=events[i][1]*256+events[i][2]
            if not 1<=pause<=32767 or (n<len(releases)-1 and pause!=1):return None
            delay=pause;i+=1
        steps.append({'usage':press[3],'modifiers':mods,'delay':delay})
    return steps if 1<=len(steps)<=64 else None

def plan_macro(data,baseline,index,name,steps):
    if digest(data)!=baseline: raise ValueError('Macros changed on the keyboard. Please retry.')
    existing=parse_macros(data)
    if index is None:
        index=next((i for i in range(256) if i not in existing),None)
        if index is None: raise ValueError('No macro slots available')
    else:
        integer(index,0,255,'macro')
        if index not in existing: raise ValueError('That macro no longer exists')
        if decode_steps(existing[index]['events']) is None: raise ValueError('This macro was made by another editor and is read-only')
    payload=encode_macro(name,steps)
    occupied=[(m['offset'],m['offset']+m['length']) for m in existing.values()]
    # Preserve the old allocation until the directory commit succeeds.
    offset=next((a for a in range(1024,4097-len(payload)) if all(a+len(payload)<=lo or a>=hi for lo,hi in occupied)),None)
    if offset is None: raise ValueError('Not enough free keyboard memory to save this macro safely. Shorten it or delete an unused macro.')
    after=bytearray(data); after[offset:offset+len(payload)]=payload
    after[index*4:index*4+4]=offset.to_bytes(2,'little')+len(payload).to_bytes(2,'little')
    return bytes(after),index

def plan_delete(data,baseline,index,keypages):
    if digest(data)!=baseline: raise ValueError('Macros changed on the keyboard. Please retry.')
    integer(index,0,255,'macro'); macros=parse_macros(data)
    if index not in macros: raise ValueError('That macro no longer exists')
    for page in keypages:
        for p in range(126):
            record=page[p*4:p*4+4]
            if record[0]==3 and record[3]==index: raise ValueError('This macro is assigned to a key. Change that assignment before deleting it.')
    after=bytearray(data); after[index*4:index*4+4]=bytes(4)
    return bytes(after)
