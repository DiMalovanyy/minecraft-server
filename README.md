# minecraft-server

K8s based minecraft server with ssl proxy server for communicate with core (.jar) file.

### Files:
* [K8s specs](https://github.com/DiMalovanyy/minecraft-server/tree/main/k8s) (Note: now used only minecraft-*.yml)
* [Redirector client and server](https://github.com/DiMalovanyy/minecraft-server/tree/main/redirector)
* [Current Image](https://hub.docker.com/layers/dmytromalovanyi/minecraft-server-core/v3/images/sha256-533fe7dc05bb5d7870122b2d8aad1316a807df590131d2d19ec6d508553fdd16?context=repo)


## TODO List:
- [x] Create k8s specs
- [x] Create Base docker image
- [ ] Add MySql deployment to cluster
- [ ] Redirector
  - [x] Create base redirector ssl server proxy
  - [x] Create redirector client
  - [ ] K8s API
    - [ ] ssl cert finding in cluster
    - [ ] Persistent volume find in cluster
  - [ ] SSL
  - [ ] Commands (Add command to redirector proxy not related to Minecraft) (/red* prefix)
    - [ ] (/red-save-world) Save worlds backups in persistent volume)
    - [ ] (/red-change-world <world_name>) Replace current world with world from persistent volume
    - [ ] Add plugins dynamicaly (Need to think about it)
    
    
## Screenshots

###  Redirecotor:
![Redirecror](https://github.com/DiMalovanyy/minecraft-server/tree/main/img/redirector.png)
