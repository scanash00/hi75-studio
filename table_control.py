"""Whitelisted stock keymap/macro operations. Called under the device lock."""
import json,os,time
from pathlib import Path
from keymap_protocol import digest,parse_macros,decode_steps,patch_key,plan_macro,plan_delete
BACKUPS=Path('/var/lib/hi75-studio/backups')

def page_read(fd,command,bank,feature):
    if command not in (0x83,0x85) or type(bank) is not int or not 0<=bank<8: raise ValueError('Invalid read')
    group,page=divmod(bank,2) if command==0x83 else (0,bank)
    header=bytes([6,command,group,0,1,page,0,2])
    for attempt in range(3):
        try:
            feature(fd,header+bytes(512));time.sleep(.05)
            response=feature(fd,bytes([6])+bytes(519),True)
            if len(response)!=520 or response[:8]!=header: raise ValueError('Incomplete keyboard reply')
            return response[8:]
        except (OSError,ValueError):
            if attempt==2: raise
            time.sleep(.1)

def stable_page(fd,command,bank,feature):
    first=page_read(fd,command,bank,feature)
    if first!=page_read(fd,command,bank,feature): raise RuntimeError('Keyboard data changed while reading. Please retry.')
    return first

def snapshot(fd,feature):
    keys=[stable_page(fd,0x83,n,feature) for n in range(8)]
    macros=b''.join(stable_page(fd,0x85,n,feature) for n in range(8))
    return keys,macros

def result(keys,data):
    error=None
    try: macros=parse_macros(data)
    except ValueError as exc: macros={};error=str(exc)
    return {'keypages':[p.hex() for p in keys],'key_baselines':[digest(p) for p in keys],
            'macro_baseline':digest(data),'macros':[{'index':i,'name':m['name'],'steps':decode_steps(m['events']),
            'event_count':len(m['events'])} for i,m in macros.items()],
            'macro_error':error,'free_bytes':3072-sum(m['length'] for m in macros.values()),'source':'keyboard'}

def backup(keys,data,operation):
    BACKUPS.mkdir(parents=True,exist_ok=True,mode=0o700)
    path=BACKUPS/(str(time.time_ns())+'-'+operation+'.json')
    with path.open('x') as stream:
        os.fchmod(stream.fileno(),0o600)
        json.dump({'keypages':[p.hex() for p in keys],'macros':data.hex()},stream)
        stream.flush();os.fsync(stream.fileno())
    fd=os.open(BACKUPS,os.O_RDONLY|os.O_DIRECTORY)
    try: os.fsync(fd)
    finally: os.close(fd)
    return path

def write_page(fd,command,bank,payload,feature):
    if command==3 and bank in (0,2): group,page=bank//2,0
    elif command==5 and type(bank) is int and 0<=bank<8: group,page=0,bank
    else: raise ValueError('Unsupported write destination')
    if len(payload)!=512: raise ValueError('Invalid page size')
    # Never retry a write: its completion may be uncertain even when ioctl fails.
    write_error=None
    try: feature(fd,bytes([6,command,group,0,1,page,0,2])+payload)
    except OSError as exc: write_error=exc
    time.sleep(.6)
    actual=stable_page(fd,0x83 if command==3 else 0x85,bank,feature)
    if actual!=payload: raise RuntimeError('Keyboard did not confirm the saved page. The write was not repeated.' + (f' USB: {write_error}' if write_error else ''))

def run(fd,operation,request,feature):
    keys,data=snapshot(fd,feature)
    if operation=='tables': return result(keys,data)
    if not isinstance(request,dict): raise ValueError('Invalid request')
    if operation=='remap':
        bank=request.get('bank')
        if type(bank) is not int or bank not in (0,2): raise ValueError('Unsupported keymap')
        after=patch_key(keys[bank],request.get('baseline'),request.get('position'),request.get('action',{}),parse_macros(data),bank)
        if after!=keys[bank]:
            path=backup(keys,data,operation)
            try: write_page(fd,3,bank,after,feature)
            except Exception as exc: raise RuntimeError(f'{exc} Original data is backed up at {path}') from exc
            keys[bank]=after
    elif operation in ('macro-save','macro-delete'):
        if operation=='macro-save':
            after,index=plan_macro(data,request.get('baseline'),request.get('index'),request.get('name'),request.get('steps'))
        else:
            after=plan_delete(data,request.get('baseline'),request.get('index'),keys)
        changed=[n for n in range(8) if data[n*512:n*512+512]!=after[n*512:n*512+512]]
        if changed:
            path=backup(keys,data,operation)
            try:
                # Payload first, directory last: incomplete saves retain the old macro.
                for n in sorted(changed,key=lambda n:(n<2,n)):
                    write_page(fd,5,n,after[n*512:n*512+512],feature)
            except Exception as exc: raise RuntimeError(f'{exc} Original data is backed up at {path}') from exc
            data=after
    else: raise ValueError('Unknown table operation')
    answer=result(keys,data)
    if operation=='macro-save':answer['saved_index']=index
    return answer
