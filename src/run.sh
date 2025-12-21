#!/usr/bin/env bash

set -x
source <(curl -SsL https://install.xiechengqi.top/tool/common.sh)

BASEPATH=`dirname $(readlink -f ${BASH_SOURCE[0]})` && cd $BASEPATH

INFO "pwd" && pwd
INFO "ls -alht" && ls -alht

name="chromium"
# docker rm -f ${name}
docker run -itd \
  --restart=always \
  -e IF_IDE_ON="false" \
  -e IF_CCSWITCH_ON="false" \
  -e IF_DUFS_ON="false" \
  -e IF_SOCKS_PROXY="false" \
  -e IF_CURSOR_CLI_ON="false" \
  -e IF_GEMINI_CLI_ON="false" \
  -e IF_CODEX_CLI_ON="false" \
  -e IF_CLAUDE_CLI_ON="false" \
  -e IF_GOLANG_ON="false" \
  -e IF_NODEJS_ON="false" \
  -e IF_JUPYTER_ON="false" \
  -e IF_NPS_ON="false" \
  -e IF_NPC_ON="false" \
  -e IF_YPROMPT_ON="false" \
  -e IF_TERMINAL_ON="true" \
  -e TERMINAL_USER="root" \
  -e TERMINAL_PASSWORD="123123" \
  -e LANG=C.UTF-8 \
  -e CHROMIUM_CLEAN_SINGLETONLOCK=true \
  -e CHROMIUM_START_URLS="chrome://version" \
  -v ${PWD}/start.sh:/app/start.sh \
  --name ${name} fullnode/remote-chromium-ubuntu:latest

docker ps

sleep 10

docker ps
docker logs --tail 30 ${name}

# cat /etc/os-release
sleep 10

# pwd
# ls
docker exec -i ${name} "pwd"
docker exec -i ${name} "ls --color=auto -alht"
docker exec -i ${name} "/app/start.sh"

for i in $(ls -d */ | grep -v '__pycache__' | sed 's/\/$//;s/^src\///')
do
docker cp ${name}:/app/models/${i}.json ../${i}.json
done
