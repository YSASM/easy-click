import json,os

class CONFIG():
    def __init__(self) -> None:
        self.path = os.path.dirname(__file__)+'/contect.json'
        self.f = open(self.path,'r',encoding="utf-8")
        # self.fw = open(self.path,'w',encoding="utf-8")
        self.config = json.loads(self.f.read())
        self.host = self.config['host']
    def beStr(self,j):
        return str(j).replace("'","\"")
    def write(self):
        self.config['host'] = self.host
        open(self.path,'w',encoding="utf-8").write(self.beStr(self.config))
def choosePort():
    return input('Enter port:')
def chooseHost(config):
    hosts = config.host
    print("Choose host:")
    for host in hosts:
        print('{}:{}'.format(hosts.index(host),host))
    index = input("Choose host:")
    try:
        index = int(index)
        host = hosts[index]
    except:
        return chooseHost(config)
    if(host=="other"):
        host=input('Enter host:')
        config.host[1] = host
        config.write()
    port = choosePort()
    return '{}:{}'.format(host,port)

def main():
    method = input('0:pair\n1:connect\n')
    if(method=="0"):
        method = "pair"
    elif(method=="1"):
        method = "connect"
    else:
        return main()
    config = CONFIG()
    ip = chooseHost(config)
    os.system("adb {} {}".format(method,ip))
    os.system('pause')
if __name__ == "__main__":
    main()