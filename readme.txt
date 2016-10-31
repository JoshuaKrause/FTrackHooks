---------------------------------
FTrack Hooks
by Joshua Krause
---------------------------------

This is a collection of three pipeline scripts I wrote for FTrack. They are based upon a specific file structure which can be modified within the script.

Included:

outputManagerHook_v04.py
This script links a local image or movie file to FTrack as an asset. This allows it to previewed without the typical file compression used by FTrack's built-in web encoder. This works best in conjunction with the associated DJVViewer hook. 

transferFileHook_v05.py
This script scans the specified OUT directory for files and allows the user to transfer them to another server. This was done mainly because the VFX department had to transfer output files to the editors' server.

DJVViewer_hook_v03.py
This hook opens a local file in DJVViwer. The file needs to be linked using the outputManager hook. 