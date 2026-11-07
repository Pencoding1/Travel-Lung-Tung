"""Opaque private workspace archive. Never print or inspect file contents."""
import json
import os
import stat
import time
import zipfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'docs/handover/releases/private/TVLT_2026_full_private_2026-10-29.zip'
TEMP=OUT.with_suffix('.zip.partial')
PRIVATE_EXCERPT='KEY_EXPOSURE_EXCERPT_PRIVATE.txt'

def main():
 if OUT.exists() or TEMP.exists():raise RuntimeError('output_exists_no_overwrite')
 files=[];skipped_venvs=[];skipped_links=0;skipped_private=0;total=0
 for base,dirs,names in os.walk(ROOT,followlinks=False):
  folder=Path(base)
  keep=[]
  for name in dirs:
   child=folder/name
   if child.is_symlink() or getattr(child.lstat(),'st_file_attributes',0)&getattr(stat,'FILE_ATTRIBUTE_REPARSE_POINT',0x400):
    skipped_links+=1;continue
   if name.lower() in {'.venv','venv','env'} or name.lower().startswith('.venv-') or (child/'pyvenv.cfg').is_file():
    skipped_venvs.append(str(child.relative_to(ROOT)));continue
   keep.append(name)
  dirs[:]=keep
  for name in names:
   path=folder/name
   if path in {OUT,TEMP}:continue
   if name==PRIVATE_EXCERPT:
    skipped_private+=1;continue
   info=path.lstat()
   if stat.S_ISLNK(info.st_mode) or not stat.S_ISREG(info.st_mode):
    skipped_links+=1;continue
   files.append((path,info.st_size));total+=info.st_size
 print(json.dumps({'phase':'inventory','files':len(files),'source_bytes':total,'excluded_venv_directories':len(skipped_venvs),'excluded_links_or_special':skipped_links,'excluded_private_incident_excerpt':skipped_private,'env_files':sum(p.name=='.env' or p.name.startswith('.env.') for p,_ in files)}),flush=True)
 OUT.parent.mkdir(parents=True,exist_ok=True)
 started=time.monotonic()
 # Stored entries preserve bytes and keep large binaries quick to package.
 with zipfile.ZipFile(TEMP,'x',compression=zipfile.ZIP_STORED,allowZip64=True,strict_timestamps=False) as archive:
  for index,(path,_) in enumerate(files,1):
   archive.write(path,'TVLT_2026/'+path.relative_to(ROOT).as_posix())
   if index%5000==0:print(json.dumps({'phase':'packing','written':index,'total':len(files)}),flush=True)
 with zipfile.ZipFile(TEMP) as archive:
  if len(archive.infolist())!=len(files):raise RuntimeError('entry_count_mismatch')
  if archive.testzip() is not None:raise RuntimeError('crc_failed')
 TEMP.rename(OUT)
 print(json.dumps({'phase':'complete','archive':str(OUT),'files':len(files),'archive_bytes':OUT.stat().st_size,'crc':'pass','seconds':round(time.monotonic()-started,1),'contains_secrets':True}),flush=True)

if __name__=='__main__':main()
