# easy-click

## 简介

easy-click 是一个基于 pyqt 的安卓模拟器脚本框架，用于适应大多数需要使用脚本进行重复工作的情况。

## 脚本语法
easy-click的脚本为一个简单的指令集，每个指令之间以换行分隔。
[arg] 为必填参数
(arg)为可选参数
```
# 回到主页
HOME
# 返回
BACK
# 结束脚本
END
# 标签
TAG [标签名]
# 跳转标签
GO [标签名]
# 匹配图片
FIND_IMAGE [图片地址，如：image0.png] [存放坐标的变量名，如：image0] (如果匹配到跳转的标签名) (如果匹配不到跳转的标签名)

# 点击
CLICK [坐标变量名，如：image0]
CLICK [x坐标] [y坐标]

# 等待(等待时间会自动加入+-(0.1-0.9)的随机数)
WAIT [等待时间，单位：秒]
```

## 示例
```
HOME
TAG START
FIND_IMAGE image0.png image0 HAVE_IMAGE NOT_IMAGE
TAG NEXT
WAIT 3
END

TAG HAVE_IMAGE
CLICK image0
GO NEXT

TAG NOT_IMAGE
BACK
GO START
```

## 构建
```
pip install -r requirements.txt
python build.py
```