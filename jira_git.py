import subprocess
import re
import os
import logging
import urlparse
import xmlrpclib
import sys
import ConfigParser

class Configured:
  def __init__(self, filename):
    self.filename = filename
 
  def get_value(self, section, key):
    try:
      cfg = ConfigParser.ConfigParser()
      cfg.read(self.filename)
      value = cfg.get(section, key)
    except:
      return None
    return value
    

  def save_value(self, section, key, value):
    try:
      cfg = ConfigParser.ConfigParser()
      cfg.read(self.filename)
    except Exception, e:
      logging.warning("Failed to read %s" %s self.filename)
      logging.debug(e)
      return

    try:
      cfg.add_section(section)
    except ConfigParser.DuplicateSectionError,e:
      logging.debug("Section '%s' already exists in '%s'", section, self.filename)

    try:
      cfg.set(section, key, value)
    except Exception, e:
      logging.warning("Failed to add '%s' to '%s'", key, self.filename)
      logging.debug(e)
    
    try:
      with open(cfg_file_name, 'wb') as f
        cfg.write(f)
    except Exception, e:
      logging.warning("Failed to write '%s'='%s' to file %s", key, value, self.filename)
      logging.debug(e)
      return

class CLI:
  def execute(self, cmd):
    try:
        proc = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE)
        return proc.stdout.read().rstrip('\n')

    except Exception, e:
	logging.error("Failed to execute command '%s'", cmd)
        logging.debug(e)


class Git(CLI):

  def is_enabled(self, ref = None):
    return True
  
  def last_commit_id(self):
    return self.execute("git log --pretty=format:%H -1")
  
  def commit_id_range(self, start, end):
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
    value = self.execute("git config '" + name + "'")
    if value.strip() == "":
      value = None
    return value

  def commit_message_from_file(self, filename):
    if os.path.exists(filename):
      try:
        with open(filename) as f:
          return f.read()

      except Exception, e:
        logging.error("Failed to open file '%s'", filename)
        logging.debug(e)    
    return None
  
  def commit_message(self, id = None):
    if id == None:
      id = self.last_commit_id()
    return self.execute("git rev-list --pretty --max-count=1 " + id)

  def commit_from_file(self, filename):
    msg = self.commit_message_from_file(filename)
    if msg == None:
      return None
    else:
      return Commit(None, msg, self.get_username())

  def commit(self, id = None):
    return Commit(id, self.get_author_username(id), self.commit_message(id))

  def commit_range(self, start, end):
    ids = commit_id_range(start, end)
    return map(lambda i: self.commit(i), ids)


class Jira:  
  @staticmethod
  def fromGitConfig(git):
    return Jira(git.get_config("jira.url"), git.get_config("jira.username"), git.get_config("jira.password"), git.get_config("jira.project"))

  @staticmethod
  def fromConfiguration(filename = None):
    if filename == None:
      filename = os.environ['HOME'] + "/.jirarc"
    config = Configured(filename)
    url = config.get_value("jira", "url")
    username = config.get_value("jira", "username")
    password = config.get_value("jira", "password")
    project = config.get_value("jira", "project")
    return Jira(url, username, password, project)
  
  def __init__(self, url, username, password, projectKey):
    self.url = url
    self.username = username
    self.password = password
    self.projectKey = projectKey
    
  def validate(self, commit):
    try:
	proxy = xmlrpclib.ServerProxy(urlparse.urljoin(self.url, '/rpc/xmlrpc'))
	acceptance, comment = proxy.commitacc.acceptCommit(self.username, self.password, commit.username, self.projectKey, commit.message).split('|')
    except Exception,e:
        logging.error(e)
	acceptance, comment = ['false', 'Unable to connect to the JIRA server at "' + self.url + '".']
    logging.info(comment)
    if acceptance == "false":
      commit.set_error(comment)
    return acceptance == "true"


class Commit:
  def __init__(self, id, message, username):
    self.id = id
    self.message = message
    self.username = username
    self.error = None

  def set_error(self, message):
    self.error = message

  def has_error(self):
    self.error != None

  def __repr__(self):
    return "Commit: id: %s, username %s, message %s" % (self.id, self.username, self.message)
 
class Validator:

  def __init__(self, jira = None):
    self.git = Git()    
    if jira == None:
      jira = Jira.fromGitConfig(git)
    self.jira = jira

  def commit_msg(self, filename):
    if self.git.is_enabled():
      commit = self.git.commit_from_file(filename)
      if commit == None:
        return 1
      elif not self.jira.validate(commit):
        print >> sys.stderr, "Commit rejected, error was %s" % (commit.error)
        return 1
    return 0

  def update(self, ref, start, end):
    if self.git.is_enabled(ref):
     commits = self.git.commit_range(start, end)
     for c in commits:
       self.jira.validate(c)
     
     withErrors = filter(lambda c: c.has_error())
     if len(withErrors) > 0:
       for c in commits:
         print >> sys.stderr, "Commit with id %s rejected, error was %s" % (c.id, c.error)
       return 1               
     return 0

if __name__ == "__main__":
  #Change this if you need to specify a different jira than the one configured in 
  jira = None  

  # Change this value to "CRITICAL/ERROR/WARNING/INFO/DEBUG/NOTSET" 
  # as appropriate.
  # loglevel=logging.INFO
  loglevel=logging.DEBUG
  myname = os.path.basename(sys.argv[0])
  logging.basicConfig(level=loglevel, format=myname + ":%(levelname)s: %(message)s")  
  v = Validator(jira)
  if myname == "commit-msg":
    v.commit_msg(sys.argv[1])
  elif myname == "update":
    if len(sys.argv) < 4:
      logging.error("update hook called with incorrect no. of parameters")
      sys.exit(1)
    else:
      ref = sys.argv[1] # This is of the form "refs/heads/<branchname>"
      old_commit_id = sys.argv[2]
      new_commit_id = sys.argv[3]
      sys.exit(v.update(ref, old_commit_id, new_commit_id))
  else:
    print >> sys.stderr, "Unknown script name"
    sys.exit(1)

