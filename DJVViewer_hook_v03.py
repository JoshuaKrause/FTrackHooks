'''
DJV View Action v.02
by Joshua Krause

This Ftrack Connect hook registers DJV View with Ftrack. 
When run with an image sequence asset selected, DJV View opens the asset.
If an inappropriate object is selected, the DJV View application launches with no file.
'''

import logging
import getpass
import sys
import pprint
import os

import ftrack
import ftrack_connect.application


class DJVViewerAction(object):
	'''
	Launch DJVViewer action.
	'''
	
	# Unique action identifier.
	identifier = 'djvviewer-launch-action'
	
	def __init__(self, applicationStore, launcher):
		'''
		Initialize action.
		'''
		super(DJVViewerAction, self).__init__()
		self.logger = logging.getLogger(
			__name__ + '.' + self.__class__.__name__
		)
		
		self.applicationStore = applicationStore
		self.launcher = launcher
		
		if self.identifier is None:
			raise ValueError('The action must be given an identifier.')
			
	def register(self):
		'''
		Register action with Ftrack.
		'''
		ftrack.EVENT_HUB.subscribe(
			'topic=ftrack.action.discover and source.user.username={0}'.format(
				getpass.getuser()
			),
			self.discover
		)
		ftrack.EVENT_HUB.subscribe(
			'topic=ftrack.action.launch and source.user.username={0} '
			'and data.actionIdentifier={1}'.format(
				getpass.getuser(), self.identifier
			),
			self.launch
		)
		
	def discover(self, event):
		''' 
		Returns a list of applicable applications and their accompanying attributes, such as label, version, etc. 
		'''
		items = []
		applications = self.applicationStore.applications
		applications = sorted(
			applications, key=lambda application: application['label']
		)
		
		for application in applications:
			applicationIdentifier = application['identifier']
			label = application['label']
			items.append({
				'actionIdentifier': self.identifier,
				'label': label,
				'variant': application.get('variant', None),
				'description': application.get('description', None),
				'icon': application.get('icon', 'default'),
				'applicationIdentifier': applicationIdentifier
			})
			
		selection = event['data'].get('selection', [])
		entityType = selection[0]['entityType']
		if len(selection) == 1 and entityType == 'assetversion':	
			return {
				'items': items
			}
		
	def launch(self, event):
		''' 
		Passes launch information to the launcher.
		Registers the application to launch and any additional data required for the launch.
		'''
		# Prevent further processing by other listeners.
		event.stop()
		
		# The application selected.
		application_identifier = event['data']['applicationIdentifier']
		
		# If we have an asset_version selected, pass it to the launcher as context.
		context = event['data'].copy()
		context['source'] = event['source']
		if context['selection'][0]['entityType'] == 'asset_version' or context['selection'][0]['entityType'] == 'assetversion':
			assetVersion = ftrack.AssetVersion(context['selection'][0]['entityId'])
			context['selection'] = [{'entityId': context['selection'][0]['entityId'], 'entityType': context['selection'][0]['entityType']}]
			
		return self.launcher.launch(application_identifier, context)
		
class ApplicationStore(ftrack_connect.application.ApplicationStore):
	'''
	Store used to find and keep track of available applications.
	'''
	
	def _discoverApplications(self):
		'''
		Return a list of applications that can be launched from this host.
		'''
		applications = []
		if sys.platform == 'darwin':
			prefix = ['/', 'Applications']
			
			applications.extend(self._searchFilesystem(
				expression=prefix + [
					'DJVViewer*', 'djv_view.app'
				],
				label='DJV View',
				applicationIdentifier='djv_view'
			))
		elif sys.platform == 'win32':
			prefix = ['C:\\', 'Program Files.*']

			applications.extend(self._searchFilesystem(
				expression=(
					prefix +
					['djv-1.1.0-Windows-64', 'bin', 'djv_view.exe']
				),
				label='DJV View',
				applicationIdentifier='djv_view'
			))
			
		self.logger.debug(
			'Discovered applications:\n{0}'.format(
				pprint.pformat(applications)
			)
		)
		return applications
		
class ApplicationLauncher(ftrack_connect.application.ApplicationLauncher):
	
	def _getApplicationLaunchCommand(self, application, context=None):
		'''
		Returns a command to launch the selected application.
		If a file is selected to open, it will be appended to the command.
		'''		
		# Inherit the base command from the ApplicationLauncher.
		command = super(ApplicationLauncher, self)._getApplicationLaunchCommand(application, context)[0]
		
		# Figure out if the command should be started with a file path.
		if command is not None and context is not None:
			# If our selection is an asset_version and its type is an image sequence, get its component.
			selection = context['selection'][0]
			if selection['entityType'] == 'asset_version' or selection['entityType'] == 'assetversion':
				self.logger.debug(u'Launching action with context {0!r}'.format(context))
				try:
					entityId = selection['entityId']
					aVersion = ftrack.AssetVersion(entityId)
					if aVersion.getAsset().getType().getShort() == 'img':
						component = None
						try:
							components = aVersion.getComponents()
							for c in components:
								if c.getName() == 'Server link':
									component = c
						except:
							pass

						# If we have a component, append its path to the command.
						if component:
							path = component.getFilesystemPath()
							self.logger.info(u'Launching application with file {0!r}'.format(path))
							command = command + ' ' + path
						else:
							self.logger.warning(
								'Unable to find an appropriate component when '
								'launching with latest version.'
							)
				except:
					pass
					
		return command
		
def register(registry, **kw):
	'''
	Register action in Connect.
	'''	
	logger = logging.getLogger(
		'ftrack_plugin:ftrack_connect_adobe_hook.register'
	)
	# Validate that registry is an instance of ftrack.Registry. If not,
	# assume that register is being called from a new or incompatible API and
	# return without doing anything.
	if not isinstance(registry, ftrack.Registry):
		logger.debug(
			'Not subscribing plugin as passed argument {0!r} is not an '
			'ftrack.Registry instance.'.format(registry)
		)
		return
		
	applicationStore = ApplicationStore()
	
	launcher = ApplicationLauncher(applicationStore)
	
	action = DJVViewerAction(applicationStore, launcher)
	action.register()
