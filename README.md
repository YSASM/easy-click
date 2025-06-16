# easy-click

## 简介

easy-click 是一个基于 pyqt 的安卓模拟器脚本框架，用于适应大多数需要使用脚本进行重复工作的情况。
## 脚本语法
easy-click的脚本为一个简单的指令集，每个指令之间以换行分隔。
[arg] 为必填参数
(arg)为可选参数
```
# 启动app
START [包名]
# 调用其他脚本
IMPORT [脚本名 如：script1]
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
WAIT_IMAGE [图片地址，如：image0.png] [存放坐标的变量名，如：image0] (如果匹配到跳转的标签名) (如果匹配不到跳转的标签名) (循环次数:一秒钟匹配一次)
HAS_IMAGE [图片地址，如：image0.png] [图片地址，如：image1.png] ...  | (如果匹配到跳转的标签名) (如果匹配不到跳转的标签名)

# HAS_IMAGE可以同时匹配多个图片 HAS_IMAGE 后将需要匹配的图片一个个列出来 后面接 | 符号， | 符号后面接是否两个标签名

# 点击
CLICK [坐标变量名，如：image0]
CLICK [x坐标] [y坐标]

# 滑动
SWIPE [起始坐标变量名，如：image0] [结束坐标变量名，如：image1]

# 等待(等待时间会自动加入+-(0.1-0.9)的随机数)
WAIT [等待时间，单位：秒]

# 日志
LOG [日志内容]
INFO [日志内容]
WARN [日志内容]
ERROR [日志内容]

# 赋值
SET VAR [变量名] [数值]
SET XY [变量名] [X数值] [Y数值]

# 计算
CALC XY [变量名] [x/y] [运算符] [变量名/数值] [保存到变量名]
CALC VAR [变量名/数值] [运算符] [变量名/数值] [保存到变量名]

# 随机数
RANDOM [开始范围] [结束范围] [保存到变量名]

# 条件判断
IF [变量名/数值] [条件判断符] [变量名/数值] [条件成立跳转标签] [条件不成立跳转标签]
```

## 标签语法糖
```
CLICK CONTINU END
# 接在条件判定后面,比如下方，实现了一个循环等待image0
TAG LOOP
FIND_IMAGE image0.png image0 CLICK LOOP

# 假如需要等待几秒再点击
TAG LOOP
FIND_IMAGE image0.png image0 CONTINU LOOP
WAIT 3
CLICK image0
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

```
RANDOM 1 3 num
RANDOM 1 3 num2
SET XY a 1 num2
LOG a
CALC XY a x + num a
LOG a
```

## 构建
```
pip install -r requirements.txt
python build.py
```