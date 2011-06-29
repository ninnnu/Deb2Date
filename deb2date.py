#!/usr/bin/python
import os
import gzip
import apt_pkg # VersionCompare
import urllib2
from debian import debfile # Reading changelogs

servers = [{'name':'localhost', 'architecture': 'i386', "repos": []}, # Leave repos empty
           {'name':'server2.example.com', 'arcitecture': 'i386', "repos": []}]

print "Fetching 'dpkg -l' and apt-sources"
for server in servers:
    os.system("ssh  "+server['name']+" dpkg -l > "+server['name']+".list")
    os.system("ssh  "+server['name']+" cat /etc/apt/sources.list > "+server['name']+".sources")
    os.system("ssh  "+server['name']+" cat /etc/apt/sources.list.d/* >> "+server['name']+".sources")

print "Fetching repo-contents"
fetched_repos = []
i = 0
for server in servers:
    f_sources = open(server['name']+".sources",'r')
    sources = f_sources.readlines()
    f_sources.close()
    os.unlink(server['name']+".sources") # source-file is no longer needed. It's easier to delete now than later.
    for line in sources:
        if(line[0:4] == "deb "):
            repoparts = line[4:].split(' ')
            repoparts[-1] = repoparts[-1].strip("\n")
            repourl = repoparts[0] + "/dists/" # APT-repos seem to always have this to.
            repourl = repourl + '/'.join(repoparts[1:]) + "/binary-"+server['architecture']
            servers[i]['repos'].append(repourl)
            print repourl # Mostly for debugging purposes
            if(repourl not in fetched_repos):
                repoweb = urllib2.urlopen(repourl + "/Packages.gz") # Fetch list of available packages
                repo_f = file(repourl.replace('/','_'), 'wb') # UNIX-filenames can't contain /. Workaround
                repo_f.write(repoweb.read())
                repo_f.close()
                # Gunzip
                repo_gz = gzip.GzipFile(repourl.replace('/','_'))
                repo_tmp = repo_gz.read()
                repo_gz.close()

                repo_f = open(repourl.replace('/','_'), 'wb')
                repo_f.write(repo_tmp)
                repo_f.close()
                fetched_repos.append(repourl)
    i = i+1

print "Finding outdated packages"
apt_pkg.InitSystem()
i = 0
for server in servers:
    server['packages'] = {}

    installed_f = open(server['name']+".list",'r') # Read server's list of currently installed packages.
    installed = installed_f.readlines()
    installed_f.close()
    os.unlink(server['name']+".list") # No longer needed. Easier to delete now...
    try:
        version_loc = installed[3].find("Vers") # Determine location of version-string
    except:
        print "Package-status of "+server["name"]+" couldn't be read."
        i = i+1
        continue
    for line in installed:
        if(line[0:2] == "ii"):
            name = line[4:line.find(' ', 4)]
            version = line[version_loc:line.find(' ', version_loc)]
            server['packages'][name] = version
    
    out_of_date = {}
    for repo in server['repos']:
        repo_f = open(repo.replace('/','_'), 'r')
        repolines = repo_f.readlines()
        repo_f.close()
        package = {}
        for line in repolines:
            if(line[0:8] == "Package:"):
                if package != {}:
                    if(package['name'] in server['packages']):
                        if(apt_pkg.VersionCompare(server['packages'][package['name']], package['version']) == -1):
                            if(package['name'] not in out_of_date):
                                out_of_date[package['name']] = [package]
                            else:
                                if(out_of_date[package['name']][-1]['version'] != package['version']):
                                    out_of_date[package['name']].append(package) # Include only differing versions.
                package = {}
                package['name'] = line[9:].strip()
            elif(line[0:8] == "Version:"):
                package['version'] = line[9:].strip()
            elif(line[0:9] == "Filename:"):
                package['url'] = repo[0:repo.find("dists")] + line[10:].strip()
    servers[i]['outdated'] = out_of_date
    servers[i]['packages'] = server['packages'] 
    i = i+1

print "Fetching changelogs & Generating report"
report = open("report.html", "w")
report.write("<html><head><title>deb2date update report</title></head><body>\n")
for server in servers:
    report.write("<h1>"+server['name']+"</h1>\n")
    if("outdated" not in server): # Version-information couldn't be fetched for the server
        report.write("'dpkg -l' couldn't be fetched for "+server['name'])
        continue
    for package in server['outdated']:
        report.write("<h2>"+package+"</h2>\n")
        report.write("Current version: "+server['packages'][package]+"<br />\n")
        report.write("Available updates: "+str(len(server['outdated'][package]))+"<br />\n")
        package = server['outdated'][package]
        i = 1 # Start counting from 1 like normal people
        for update in package:
            report.write("<h3>Update #"+str(i)+"</h3>")
            report.write("URL to .deb: <a href=\""+update['url']+"\">"+update['url']+"</a><br />\n")
            
            # Most reliable way to get changelog is retrieve the package and read the changelog from there
            package_web = urllib2.urlopen(update['url'])
            package_f = open(update["name"]+'.deb', 'wb')
            package_f.write(package_web.read())
            package_f.close()
            package_d = debfile.DebFile(update["name"]+'.deb')
            try:
                package_c = package_d.changelog()
            except:
                report.write("<pre>No changelog available</pre>\n")
                os.unlink(update["name"]+'.deb')
                continue            
            if(package_c == None): # Probably never happens, but just in case
                report.write("<pre>No changelog available</pre>\n")
                os.unlink(update["name"]+'.deb')
                continue
            changelog = ""
            for block in package_c._blocks:
                if(apt_pkg.VersionCompare(server['packages'][update['name']], str(block.version)) == -1):
                    changelog = changelog+str(block)
            report.write("<pre>"+changelog+"</pre>")
            os.unlink(update["name"]+'.deb')
            i = i+1
report.write("</body></html>")
report.close()

for repo in fetched_repos: # Delete fetched repo-package-lists
   os.unlink(repo.replace("/", "_"))
