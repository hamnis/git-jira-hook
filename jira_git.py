import subprocess
import re
import SOAPpy
import os
import logging
import urllib2

class CLI:
  def execute(self, cmd):
    try:
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
        return proc.stdout.read().rstrip('\n')

    except Exception, e:
	logging.error("Failed to execute command '%s'", cmd)
        logging.debug(e)


class Git(CLI):
  
  def last_commit_id(self):
    return self.execute("git log --pretty=format:%H -1")
  
  def commit_range(self, start, end):
    output = self.execute("git rev-list " + start + ".." + end)
    if output == "":
        return []
    
    # parse the result into an array of strings
    return string.split(output, '\n')
    

  def get_author_email(self, id = None):
    if id == None:
      id = self.last_commit_id()
    return "'%s'" % self.execute("git rev-list --max-count=1 --format=%ae " + commit_id).split("\n")[1].strip()
    
  def get_author_username(self, id = None):
    email = self.get_author_email(id)
    (username, sep, server) = email.partition('@')
    return username

  def get_user_email(self): 
    return self.get_config("user.email")

  def get_username(self):
    email = self.get_user_email()
    (username, sep, server) = email.partition('@')
    return username

  def get_config(self, name):    
    return self.execute("git config '" + name + "'")

  def commit_message_from_file(self, filename):
    if os.path.exists(filename):
      try:
        with open(filename) as f:
          return f.read()

      except Exception, e:
        logging.error("Failed to open file '%s'", commit_msg_filename)
        logging.debug(e)    
    return None
  
  def commit_message(self, id = None):
    if id == None:
      id = self.last_commit_id()
    return self.execute("git rev-list --pretty --max-count=1 " + id)


class Jira:  
  def __init__(self, url, username, password):
    self.url = url.rstrip("/")
    try:
        handle = urllib2.urlopen(self.url + "/rpc/soap/jirasoapservice-v2?wsdl")
        self.client = SOAPpy.WSDL.Proxy(handle)
        self.login(username, password)

    except Exception, e:
        logging.error("Invalid Jira URL: '%s'", url)
        logging.error(e)    
    
  
  def login(self, username, password):
    try:
      auth = self.client.login(username, password) 
      try:
        self.client.getIssueTypes(auth)
        self.loginKey = auth

      except Exception,e:
        logging.error("User '%s' does not have access to Jira issues" % username)
        logging.error(e)
        self.loginKey = None

    except Exception,e:
      logging.error("Login failed")
      logging.error(e)
      self.loginKey = None

  def get_issue(self, key):
    issue = None
    try:
      issue = self.client.getIssue(self.loginKey, key)
      logging.debug("Found issue '%s' in Jira: (%s)",  key, issue["summary"])

    except Exception, e:
        logging.error("No such issue '%s' in Jira", key)
        logging.error(e)

    return issue
  
  #TODO: Make this better. Maybe we should abort when this happens
  def check_assignment(self, issue, username):
    assignee = issue['assignee']
    return assignee == username
 
  def check_resolution(self, issue):
    if issue['resolution'] != None:
      logging.error("The issue has already been resolved, reopen, then commit/push again")
      return False
    return True

  def validate(self, keys, username):
    invalid = []
    for key in keys:
      issue = self.get_issue(key)
      if issue == None:
        invalid.append("%s did not exist." % key)
      else:
        if not self.check_assignment(issue, username):
           invalid.append("%s was not assigned to you, but was assigned to %s" % (key, issue['assignee']))
        if not self.check_resolution(issue):
           invalid.append("%s is already resolved, reopen, then try again" % key)

    return invalid



class Commit:
  def __init__(self, id, issues, username):
    self.id = id
    self.issues = issues
    self.username = username
    self.errors = []

  def has_errors(self):
    return len(self.errors) > 0

  def has_issues(self):
    return len(self.issues) > 0

  def __repr__(self):
    return "id: %s, issues : (%s), username %s, errors" % (self.id, self.issues, self.username, self.errors)

  def message(self):
    if self.id == None:
     return "Your commit message had the following jira errors\n%s" % self.errors
    elif self.has_errors:
      return "The commit with id %s had the following jira errors\n%s" % (self.id, self.errors)
    else:
      return "The commit had no errors"

class IssueParser:
  
  def __init__(self, project):
    self.pattern = re.compile("(\%s-\d\d*)" % project)
 
  def find_issues(self, commit_msg):
    iterator = self.pattern.finditer(commit_msg)
    issues = []
    for match in iterator: 
      key = match.group(1)
      issues.append(key) 
    return issues


class Validator:

  def __init__(self):
    self.git = Git()
    #self.git.get_config("jira.url")
    self.jira = createJira()
    self.parser = IssueParser("FASIT")

  def commit_msg(self, filename):
    msg = self.git.commit_message_from_file(filename)
    if msg != None:
      commit = Commit(None, self.parser.find_issues(msg), self.git.get_username())
      if not commit.has_issues(): 
        logging.error("No issues where referenced in the commit. aborting")
        return 1
      invalid = self.check_issues([commit])
      if len(invalid) > 0:
        for i in invalid:
          logging.error(i.message())
        return 1
      
    return 0

  def update(self, ref, start, end):   
    pass

  def check_issues(self, commits):
    invalid = []
    for commit in commits:
      commit.errors = self.jira.validate(commit.issues, commit.username)
      if commit.has_errors:
        invalid.append(commit)
      
    return invalid  

