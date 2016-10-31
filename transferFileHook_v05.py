'''
Transfer File: a Hook for Ftrack Connect
v05 by Joshua Krause

Scans a project's OUT directory for files.
User can select a file to copy to the TRANSFER folder.
Updates the task to APPROVED.
Sends emails to the Assistant Editor(AE), the artist, and the supervisor.
'''

import sys
import logging
import os
import threading
import getpass
import ftrack
import ftrack_api

sys.path.append('C:\Python27\Lib')

import smtplib

# Allows for multiple threads when copying files.
# Prevents script from failing due to timeout.
def async(fn):
	def wrapper(*args, **kwargs):
		thread = threading.Thread(target=fn, args=args, kwargs=kwargs)
		thread.start()
	return wrapper

class TransferFile(object):
	identifier = 'sde_transferFile'
	source_root = 'Z:/projects/'
	destination_root = 'Y:/'
	
	def __init__(self):
		super(TransferFile, self).__init__()
		
		self.logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
		
		if self.identifier is None:
			raise ValueError('The action must be given an identifier.')
		
	def launch(self, event):
		selection = event['data'].get('selection', [])
		session = ftrack_api.Session()
		
		# Create disk accessors.
		sourceAccessor = ftrack.DiskAccessor(self.source_root)
		destinationAccessor = ftrack.DiskAccessor(self.destination_root)
				
		# Check to see if there is data to process.
		# If there are no keys in values, restart the loop.
		if 'values' in event['data'] and len(event['data']['values']) > 0:
			values = event['data']['values']
			
			#If there is a selected file, process it.
			if values['transfer_file'] != '':
				finalFile = values['transfer_file']
				finalSource = '{0}\\{1}'.format(sourceAccessor.getFilesystemPath(self.sourcePath), finalFile)
				finalDestination = destinationAccessor.getFilesystemPath(self.destinationPath)
				
				#Copy the file.
				self.copyFile(finalSource, finalDestination)
				
				# Update the task status to output.
				statuses = self.project.getTaskStatuses()
				self.task.setStatus(statuses[4])

				# Send email notifications.
				self.sendNotification(finalDestination, finalFile)				
			else:
				values['output_file'] = 'None selected.'
			
			return {
				'items': [
					{ 
						'type': 'label',
						'value': 'Copying file:'
					},
					{ 
						'type': 'label',
						'value': 'File: ' + values['transfer_file']
					},
					{ 
						'type': 'label',
						'value': 'Destination: ' + self.destinationPath
					}
				]
			}

		# Validate selection and abort if not valid.
		if not self.validateSelection(selection):
			return
		
		# Clear any pre-existing variables.
		self.sourcePath = ''
		self.destinationPath = ''
		self.contactDictionary = {}
		
		# Retrieve our variables for the current task.
		self.task = ftrack.Task(selection[0]['entityId'])
		self.project = self.task.getProject();
		
		# Use the newer API to access custom attributes.
		self.task_api = session.query('Task where id is {}'.format(selection[0]['entityId']))[0]	
		project_api = session.query('Project where id is {}'.format(self.task_api['project_id']))[0];
		
		# Retrieve names and email addresses
		name = project_api['custom_attributes']['ae_name']
		address = project_api['custom_attributes']['ae_address']
		
		aeList = []
		aeEmailList = []
		
		if "," in name:
			aeList = name.split(',')
			aeEmailList = address.split(',')
		else:
			aeList.append(name)
			aeEmailList.append(address)
		
		# The assigned artists.
		assignees = self.task.getUsers()
		
		assigneeList = []
		assigneeEmailList = []
		for each in assignees:
			assigneeList.append(each.getName())
			assigneeEmailList.append(each.getEmail())
		
		# The managers
		managers = self.task.getManagers()
		
		managerList = []
		managerEmailList = []
		for each in managers:
			manager = each.getUser()
			managerList.append(manager.getName())
			managerEmailList.append(manager.getEmail())
		
		
		self.contactDictionary = {
			'manager': managerList, 
			'managerEmail' : managerEmailList, 
			'assignee': assigneeList, 
			'assigneeEmail': assigneeEmailList, 
			'ae': aeList, 
			'aeEmail' : aeEmailList }
		
		# If our task is a shot, store its name.
		if self.task.get('objecttypename') == 'Shot':
			shot = self.task.getName()
			
		# Find the parents of the current task.
		parents = self.task.getParents()
		
		for each in self.task.getParents():
			try:
				objectType = each.get('objecttypename')
				if objectType == 'Shot':
					shot = each.getName()
				if objectType == 'Act' or objectType == 'Sequence':
					act = each.getName()
				if objectType == 'Episode':
					episode = each.getName()
			except:
				objectType = each.get('entityType')
				if objectType == 'show':
					show = each.getName()
					showShort = project_api['custom_attributes']['proj']
					
		# Create variables for the old file structure and new file structure.
		try:		
			sourcePathVersionA = '{}/{}/shots/{}{}_{}_{}/out/'.format(show, episode, showShort, episode, act, shot)
			sourcePathVersionB = '{}/episodes/{}/shots/{}{}_{}_{}/out/'.format(show, episode, showShort, episode, act, shot)
			self.destinationPath = '{0}/{1}/vfx_for_editorial/{2}/'.format(show, episode, act)
		except:
			return { 'items': [{ 'type': 'label', 'value': 'Not enough variables to map current project.' }] }

		# Check to see which file structure is in use and if the output folder exists.
		if not sourceAccessor.exists(sourcePathVersionA) and not sourceAccessor.exists(sourcePathVersionB):
			return { 'items': [{ 'type': 'label', 'value': 'Output folder does exist' }] }
		else:
			if sourceAccessor.exists(sourcePathVersionA) and not sourceAccessor.exists(sourcePathVersionB):
				self.sourcePath = sourcePathVersionA
			if not sourceAccessor.exists(sourcePathVersionA) and sourceAccessor.exists(sourcePathVersionB):
				self.sourcePath = sourcePathVersionB
		
		# Generate lists of files.
		sourceListPath = sourceAccessor.list(self.sourcePath)
		destinationListPath = destinationAccessor.list(self.destinationPath)
		
		sourceList = self.cleanPath(sourceListPath)
		destinationString = '\n'.join(self.cleanPath(destinationListPath))
		
		enumeratorList = []
		for file in sourceList:
			enumeratorList.append( { 'label' : file, 'value' : file } )
		
		return {
			'items': [
				{
					'type': 'label',
					'value': 'Transfers a file to the editorial server. WARNING: Currently overwrites existing files!'
				},
				{
					'type': 'label',
					'value': 'Current shot: {0}'.format(showShort + episode + '_' + act + '_' + shot)
				},
				{
					'label': 'File',
					'type': 'enumerator',
					'name': 'transfer_file',
					'data': enumeratorList
				},
				{
					'type': 'label',
					'value': ''
				},
				{
					'type': 'label',
					'value': 'Destination: {0}'.format(destinationAccessor.getFilesystemPath(self.destinationPath))
				},
				{
					'type': 'textarea',
					'label': 'Transfer folder:',
					'value': destinationString
				},
				{
					'type': 'label',
					'value': ''
				},
				{
					'type': 'label',
					'value': 'Notification send to assistant editors: {0}'.format(' and '.join(aeList))
				},
				{
					'type': 'label',
					'value': 'Copies sent to artist(s) and supervisor(s): {0}'.format(' and '.join(assigneeList + managerList))
				}
			]
		}
		
	@async
	def copyFile(self, finalSource, finalDestination):
		command = os.system ("""xcopy /Y {0} {1} """.format(finalSource, finalDestination))
	
	# Optimizes paths for Python.
	def cleanPath(self, pathList):
		output = []
		for each in pathList:
			cleanList = each.split('/')
			output.append(cleanList[-1])
		return output
	
	# Allows Ftrack to see the plug-in
	def discover(self, event):
		selection = event['data'].get('selection', [])
		if self.validateSelection(selection):
			return { 'items': [{ 'label': 'Transfer File', 'actionIdentifier': self.identifier }] }
		
	def register(self):
		ftrack.EVENT_HUB.subscribe('topic=ftrack.action.discover and source.user.username={0}'.format(getpass.getuser()), self.discover)
		ftrack.EVENT_HUB.subscribe('topic=ftrack.action.launch and source.user.username={0} and data.actionIdentifier={1}'.format(getpass.getuser(),self.identifier), self.launch)
		
		
	def validateSelection(self, selection):
		# Check to see that our selection is a task.
		entityType = selection[0]['entityType']
		
		# Check to see that the task is a Compositing task.
		if len(selection) == 1 and entityType == 'task':
			taskName = ftrack.Task(selection[0]['entityId']).getName()
			if taskName == 'Compositing' or taskName == 'animation':
				return True
			else:
				return False
		else:
			return False
	
	# Creates a notification email.
	def sendNotification(self, finalDestination, finalFile):		
		if self.contactDictionary.get('ae') == 'None' or self.contactDictionary.get('aeEmail') == 'None':
			return
		else:
			aeName = ' and '.join(self.contactDictionary.get('ae'))
			assigneeName = ' or '.join(self.contactDictionary.get('assignee'))
			fromAddr = 'vfxsde@gmail.com'
			toAddr = self.contactDictionary.get('aeEmail')
			ccAddr = self.contactDictionary.get('assigneeEmail') + self.contactDictionary.get('managerEmail')
			subject = 'SDE VFX update: '+ finalFile +' has been transferred.'
			message = 'Dear '+ aeName +',\n\n' \
					  'Just wanted you to know that "'+ finalFile +'" has been moved to the transfer server.\n' \
					  'You can find it at:\n\n' \
					  ''+ finalDestination +'\n\n' \
					  'Contact '+ assigneeName +' if you have any questions.\n\n' \
					  'Your pal,\n' \
					  '- SDE VFX\'s automated response system'
			login = 'vfxsde'
			password = 'lisaBrundt'
			sendemail(from_addr = fromAddr,
					  to_addr_list = toAddr,
					  cc_addr_list = ccAddr,
					  subject = subject,
					  message = message,
					  login = login,
					  password = password)

# Sends the notification email.
@async					  
def sendemail(from_addr, to_addr_list, cc_addr_list,
			  subject, message,
			  login, password,
			  smtpserver='smtp.gmail.com:587'):
	header  = 'From: %s\n' % from_addr
	header += 'To: %s\n' % ','.join(to_addr_list)
	header += 'Cc: %s\n' % ','.join(cc_addr_list)
	header += 'Subject: %s\n\n' % subject
	message = header + message
	
	send_to = to_addr_list + cc_addr_list
	
	server = smtplib.SMTP(smtpserver)
	server.starttls()
	server.login(login,password)
	problems = server.sendmail(from_addr, send_to, message)

	server.quit()

def register(session, **kw):
	logger = logging.getLogger(
		'ftrack_plugin:ftrack_connect_outputManager.register'
	)
	# Validate that registry is an instance of ftrack.Registry. If not,
	# assume that register is being called from a new or incompatible API and
	# return without doing anything.
	if not isinstance(session, ftrack_api.Session):
		logger.debug(
			'Not subscribing plugin as passed argument {0!r} is not an '
			'ftrack.Registry instance.'.format(session)
		)
		return
	transferFile = TransferFile()
	transferFile.register()
	
def writeLog(string, type = 'a'):
	log = open('W:/pipeline/ftrack/log/transferFileLog.txt', type)
	log.write(string + '\n')
	log.close()