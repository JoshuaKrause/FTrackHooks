''' 
FTrack action that listen for updates on tasks and changes their status
when users are added or removed or if a new asset is uploaded.
'''

import sys
import os

path = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'ftrack-api')
sys.path.append(path)

import ftrack

def callback(event):
	
	for entity in event['data'].get('entities', []):
		# Toggle the task status when artists are assigned or unassigned.
		if entity['entityType'].lower() == 'task' and entity['action'] == 'update':
			task = ftrack.Task(id=entity.get('entityId'))
			# Ignore if the status is ON HOLD or OMITTED.
			if task.getStatus().getId() == 'a0bc2444-15e2-11e1-b21a-0019bb4983d8' or task.getStatus().getId() == 'a0bc3f24-15e2-11e1-b21a-0019bb4983d8':
				return
			else:
				# Task switches from NOT STARTED to ASSIGNED when artists are added.
				if task.getStatus().getId() == '44dd9fb2-4164-11df-9218-0019bb4983d8' and bool(task.getUsers()):
					task.setStatus(ftrack.Status(id='18002a4c-c2df-11e6-ab59-0a580a58070f'))
				# Task switches from ASSIGNED to NOT STARTED when artists are removed.
				if task.getStatus().getId() != '44dd9fb2-4164-11df-9218-0019bb4983d8' and not bool(task.getUsers()):
					task.setStatus(ftrack.Status(id='44dd9fb2-4164-11df-9218-0019bb4983d8'))
				
		# Upgrade the task status when an asset is uploaded. 
		if entity['entityType'].lower() == 'assetversion' and entity['action'] == 'update':
			task = ftrack.AssetVersion(id=entity.get('entityId')).getTask()
			# Switch status to FOR REVIEW when a new asset is uploaded
			if task.getStatus().getId() != '44dded64-4164-11df-9218-0019bb4983d8':
				task.setStatus(ftrack.Status(id='44dded64-4164-11df-9218-0019bb4983d8'))

# Subscribe to events with the update topic.
ftrack.setup()
ftrack.EVENT_HUB.subscribe('topic=ftrack.update', callback)
ftrack.EVENT_HUB.wait()