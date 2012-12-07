#!/usr/bin/env python

import json, urlparse, sys, os
from BaseHTTPServer import BaseHTTPRequestHandler, HTTPServer
from subprocess import call, Popen, PIPE, STDOUT
import smtplib
from email.mime.text import MIMEText

class GitAutoDeploy(BaseHTTPRequestHandler):

    CONFIG_FILEPATH = './GitAutoDeploy.conf.json'
    config = None
    quiet = False
    daemon = False

    @classmethod
    def getConfig(myClass):
        if(myClass.config == None):
            try:
                configString = open(myClass.CONFIG_FILEPATH).read()
            except:
                sys.exit('Could not load ' + myClass.CONFIG_FILEPATH + ' file')

            try:
                myClass.config = json.loads(configString)
            except:
                sys.exit(myClass.CONFIG_FILEPATH + ' file is not valid json')

            for repository in myClass.config['repositories']:
                if(not os.path.isdir(repository['path'])):
                    sys.exit('Directory ' + repository['path'] + ' not found')
                if(not os.path.isdir(repository['path'] + '/.git')):
                    sys.exit('Directory ' + repository['path'] + ' is not a Git repository')

        return myClass.config

    def do_POST(self):
        urls = self.parseRequest()
        for url in urls:
            path = self.getMatchingPath(url)
            self.runDeploy(path)

    def runDeploy(self, path):
        config = self.getConfig()
        rep_conf = None
        for repository in config['repositories']:
            if(repository['path'] == path):
                rep_conf = repository
                break
        if rep_conf is None:
            return
        
        if 'test_path' in rep_conf and 'test' in rep_conf:
            #self.pull(rep_conf['test_path'])
            if self.run_test(rep_conf['test_path'],
                             rep_conf['test'],
                             rep_conf.get('email', None)):
                print 'pulling to live and deploying'
                #self.pull(path)
                if 'deploy' in rep_conf:
                    self.deploy(path, rep_conf['deploy'])
        else:
            self.pull(path)
            self.deploy(path)

    def parseRequest(self):
        length = int(self.headers.getheader('content-length'))
        body = self.rfile.read(length)
        post = urlparse.parse_qs(body)
        items = []
        for itemString in post['payload']:
            item = json.loads(itemString)
            items.append(item['repository']['url'])
        return items

    def getMatchingPath(self, repoUrl):
        config = self.getConfig()
        for repository in config['repositories']:
            if(repository['url'] == repoUrl):
                return repository['path']

    def respond(self):
        self.send_response(200)
        self.send_header('Content-type', 'text/plain')
        self.end_headers()

    def report_test_results(self, res, repor_contents,
                            mail_conf=None):
        print repor_contents
        if mail_conf is not None:
            msg = MIMEText(repor_contents)
            msg['Subject'] = 'Auto pull test result: %s' % str(res)
            msg['From'] = mail_conf['user']
            msg['To'] = mail_conf['send_to']
            
            s = smtplib.SMTP(mail_conf['host'],
                             mail_conf['port']) #local_hostname=DNS_NAME.get_fqdn())
            try:
                if mail_conf['use_tls']:
                    s.ehlo()
                    s.starttls()
                    s.ehlo()
                if 'user' in mail_conf and 'password' in mail_conf:
                    s.login(mail_conf['user'],
                            mail_conf['password'])
                s.sendmail(mail_conf['user'],
                           mail_conf['send_to'],
                           msg.as_string())
                s.quit()
            except Exception as exc:
                print 'Problems mail sending:', exc
            print '\nReport mailed.'
 

    def run_test(self, path, test_command, email_conf=None):
        if(not self.quiet):
            print "\nRunning test."
        cmd = 'cd "' + path + '" && ' + test_command
        p = Popen(cmd, shell=True, stdin=PIPE, stdout=PIPE,
                  stderr=STDOUT, close_fds=True)
        call_res = p.wait()
        output = p.stdout.read()
        self.report_test_results(call_res == 0, output, email_conf)
        return call_res == 0


    def pull(self, path):
        if(not self.quiet):
            print "\nPost push request received"
            print 'Updating ' + path
        call(['cd "' + path + '" && git pull'], shell=True)

    def deploy(self, path, deploy_command):
        if(not self.quiet):
            print 'Executing deploy command'
        call(['cd "' + path + '" && ' + deploy_command], shell=True)


def main():
    try:
        server = None
        for arg in sys.argv: 
            if(arg == '-d' or arg == '--daemon-mode'):
                GitAutoDeploy.daemon = True
                GitAutoDeploy.quiet = True
            if(arg == '-q' or arg == '--quiet'):
                GitAutoDeploy.quiet = True
                
        if(GitAutoDeploy.daemon):
            pid = os.fork()
            if(pid != 0):
                sys.exit()
            os.setsid()

        if(not GitAutoDeploy.quiet):
            print 'Github Autodeploy Service v 0.1 started'
        else:
            print 'Github Autodeploy Service v 0.1 started in daemon mode'
             
        server = HTTPServer(('', GitAutoDeploy.getConfig()['port']), GitAutoDeploy)
        server.serve_forever()
    except (KeyboardInterrupt, SystemExit) as e:
        if(e): # wtf, why is this creating a new line?
            print >> sys.stderr, e

        if(not server is None):
            server.socket.close()

        if(not GitAutoDeploy.quiet):
            print 'Goodbye'

if __name__ == '__main__':
     main()
