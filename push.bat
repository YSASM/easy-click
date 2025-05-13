@echo off
git add .
git commit -m %1
git config --global http.proxy http://127.0.0.1:7890
git pull
git push
git config --global --unset  http.proxy