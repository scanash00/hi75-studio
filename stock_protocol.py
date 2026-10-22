"""Restricted HI75 stock V5 configuration protocol. No firmware/ISP commands."""
import hashlib
HEADER = bytes([6, 0x84, 0, 0, 1, 0, 0, 2])
LIMITS = {'effect':18, 'brightness':4, 'speed':4, 'palette':7}
def unpack(report):
    if len(report) != 520 or report[:8] != HEADER or report[134:136] != b'\x5a\xa5':
        raise ValueError('Keyboard returned an unrecognized configuration')
    return bytes(report[8:])
def state(payload):
    effect = payload[10]
    native = payload[5] == 0 and payload[9] == 0 and effect <= 18
    result = {'baseline':hashlib.sha256(payload).hexdigest(), 'native':native}
    if native:
        i=56+effect*2
        result.update(effect=effect, brightness=payload[i]&31, speed=payload[i+1]>>4, palette=payload[i+1]&15)
        if any(result[k]>v for k,v in LIMITS.items()): result['native']=False
    return result

def patch(payload, baseline, changes):
    if baseline != state(payload)['baseline']: raise ValueError('Settings changed on the keyboard. Please adjust again.')
    if not changes or set(changes)-LIMITS.keys(): raise ValueError('Invalid settings')
    for key,value in changes.items():
        if type(value) is not int or not 0 <= value <= LIMITS[key]: raise ValueError('Invalid '+key)
    current=state(payload)
    if not current['native'] and 'effect' not in changes: raise ValueError('Select an effect first')
    effect=changes.get('effect',payload[10]); i=56+effect*2
    result=bytearray(payload); result[5]=result[9]=0; result[10]=effect
    if 'brightness' in changes: result[i]=(result[i]&224)|changes['brightness']
    if 'speed' in changes: result[i+1]=(result[i+1]&15)|(changes['speed']<<4)
    if 'palette' in changes: result[i+1]=(result[i+1]&240)|changes['palette']
    return bytes(result)


def direct_packet(rgb):
    if not isinstance(rgb,list) or len(rgb)!=3 or any(type(v) is not int or not 0<=v<=255 for v in rgb):
        raise ValueError('RGB must contain three integers from 0 to 255')
    return bytes([6,8,0,0,1,0,0x7a,1])+bytes(rgb)*126+bytes(134)
