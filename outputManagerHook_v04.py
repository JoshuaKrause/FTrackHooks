'''
Output Manager: a Hook for Ftrack Connect
v04 by Joshua Krause

Scans a project's OUT directory for files.
User can select a file to to upload for web viewing.
Also creates a link to the local file for synergy with the accompanying DJV View hook.
'''

import logging
import getpass
import threading
import os.path
import ftrack
import ftrack_api

def async(fn):
	# Run the uploading method on a separate thread so it doesn't cause the Action to fail.
	def wrapper(*args, **kwargs):
		thread = threading.Thread(target=fn, args=args, kwargs=kwargs)
		thread.start()
	return wrapper

class OutputManager(object):
	
	identifier = 'sde_output_manager'
	
	projectRoot = 'Z:/projects/'
	outputPath = 'out'
	
	def __init__(self):
		super(OutputManager, self).__init__()
		
		self.logger = logging.getLogger(__name__ + '.' + self.__class__.__name__)
		
		if self.identifier is None:
			raise ValueError('The action must be given an identifier.')
	
	@async
	def processAsset(self, outputPath, outputFile):
		# Uploads an asset to Ftrack and links to the original on the server.
		try:
			asset = self.task.createAsset(name=outputFile, assetType ='img')
		except:
			asset = self.task.getParent().createAsset(name=outputFile, assetType ='img')
		version = asset.createVersion(taskid=self.task.getId())
		componentPath = outputPath + "\\" + outputFile 
		# Create a web viewable version, then attach the server link to it.
		ftrack.Review.makeReviewable(version, filePath=componentPath)
		linkedComponent = version.createComponent(name='Server link', path=componentPath)
		version.publish()
		
	def launch(self, event):
		selection = event['data'].get('selection', [])
		session = ftrack_api.Session()
			
		# If the event dictionary has a 'data' entry, check to see if there is a file to process.
		if 'values' in event['data'] and len(event['data']['values']) > 0:
			values = event['data']['values']
			
			# If there is a file, process it.
			if values['output_file'] != '':
				outFile = values['output_file']
				outPath = self.projectsAccessor.getFilesystemPath(self.outputPath)
				self.processAsset(outPath, outFile)
				
				# Update the status.			
				statuses = self.project.getTaskStatuses()
				self.task.setStatus(statuses[2])
				
			# If there isn't a file, nothing was selected on the previous menu.
			else:
				values['output_file'] = 'None selected.'
			return {
				'items': [
					{ 
						'type': 'label',
						'value': 'Currently uploading:'
					},
					{ 
						'type': 'label',
						'value': values['output_file']
					},
					{ 
						'type': 'label',
						'value': 'This may take a few minutes.'
					}
				]
			}			
		
		# Ensure that the selection is a task.
		if not self.validateSelection(selection):
			return
				
		# Get the task and use its parents to create path variables.
		self.task = ftrack.Task(selection[0]['entityId'])
		self.project = self.task.getProject()
		
		task_api = session.query('Task where id is {}'.format(selection[0]['entityId']))[0]	
		project_api = session.query('Project where id is {}'.format(task_api['project_id']))[0];
		
		if self.task.get('objecttypename') == 'Shot':
			shot = self.task.getName()
			
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
			pathVersionA = '{0}{1}/{2}/shots/{3}{4}_{5}_{6}'.format(self.projectRoot, show, episode, showShort, episode, act, shot)
			pathVersionB = '{0}{1}/episodes/{2}/shots/{3}{4}_{5}_{6}'.format(self.projectRoot, show, episode, showShort, episode, act, shot)
		except:
			return { 'items': [{ 'type': 'label', 'value': 'Not enough variables to map current project.' }] }

		# Create disk accessors.
		self.projectsAccessorA = ftrack.DiskAccessor(pathVersionA)
		self.projectsAccessorB = ftrack.DiskAccessor(pathVersionB)
		
		# Check to see which file structure is in use and if the output folder exists.
		if not self.projectsAccessorA.exists(self.outputPath) and not self.projectsAccessorB.exists(self.outputPath):
			return { 'items': [{ 'type': 'label', 'value': 'Output folder does exist' }] }
		else:
			if self.projectsAccessorA.exists(self.outputPath) and not self.projectsAccessorB.exists(self.outputPath):
				self.projectsAccessor = ftrack.DiskAccessor(pathVersionA)
			if not self.projectsAccessorA.exists(self.outputPath) and self.projectsAccessorB.exists(self.outputPath):
				self.projectsAccessor = ftrack.DiskAccessor(pathVersionB)
		
		# Generate a list of files in the out folder and use it to generate an enum.
		filePaths = self.projectsAccessor.list(self.outputPath)
		outputList = []

		for item in filePaths:
			pathList = item.split("\\")
			outputList.append(pathList[-1])
		
		outputPreviewList = []
		for file in outputList:
			outputPreviewList.append( { 'label' : file, 'value' : file } )
							
		return {
			'items': [
				{
					'type': 'label',
					'value': 'Upload manager creates a web viewable preview and links it back to the server.'
				},
				{
					'type': 'label',
					'value': 'Current shot: {0}'.format(showShort + episode + '_' + act + '_' + shot)
				},
				{
					'label': 'Output file',
					'type': 'enumerator',
					'name': 'output_file',
					'data': outputPreviewList
				} 
			]
		}
				
	def discover(self, event):
		# If the selection is a task, reveal the action button.
		selection = event['data'].get('selection', [])
		if self.validateSelection(selection):
			return { 'items': [{ 'label': 'Output Manager', 'actionIdentifier': self.identifier }] }
		
	def register(self):
		# Register the class with Ftrack.
		ftrack.EVENT_HUB.subscribe('topic=ftrack.action.discover and source.user.username={0}'.format(getpass.getuser()), self.discover)
		ftrack.EVENT_HUB.subscribe('topic=ftrack.action.launch and source.user.username={0} and data.actionIdentifier={1}'.format(getpass.getuser(),self.identifier), self.launch)
	
	def validateSelection(self, selection):
		# Check to see that our selection is a task.
		entityType = selection[0]['entityType']

		if len(selection) == 1 and entityType == 'task':
			taskName = ftrack.Task(selection[0]['entityId']).getName()
			if taskName == 'Compositing' or taskName == 'animation':
				return True
			else:
				return False
		else:
			return False

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
	outputManager = OutputManager()
	outputManager.register()

def writeLog(string, type = 'a'):
	log = open('W:/pipeline/ftrack/log/outputLog.txt', type)
	log.write(string + '\n')
	log.close()