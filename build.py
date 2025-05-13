"""
Python构建程序
先将py文件编译成pyd再打包防止逆向破解
"""
import os, shutil, time, sys, glob

try:
    from setuptools import setup  # 检测是否安装了cython
except:
    print("\n请先安装cython模块：pip install cython\n"); sys.exit()


def py2pyd(path):
    folder_path = os.path.dirname(path)  # 文件夹路径
    file_path = os.path.split(path)[1]  # 不带路径的文件名
    os.chdir(folder_path)
    filename = file_path.split('.py')[0]  # 文件名
    with open('setup.py', 'w') as f:  # 自动生成单独的setup.py文件
        f.write('from setuptools import setup\n')
        f.write('from Cython.Build import cythonize\n')
        f.write('setup(\n')
        f.write("name='%s',\n" % filename)
        f.write("ext_modules=cythonize('%s')\n" % file_path)
        f.write(")\n")
    os.system('python setup.py build_ext --inplace --build-lib ' + os.path.dirname(folder_path))  # py编译开始


    time.sleep(2)
    pyd_name = '%s\\%s.pyd' % (folder_path, filename)  # pyd文件名
    if os.path.exists(pyd_name): os.remove(pyd_name)  # 删除老的pyd

    amd64_pyd = glob.glob(filename + "*.pyd")  # 获取pyd文件的全名，类似***.cp38-win_amd64.pyd
    print("生成了PYD：" + amd64_pyd[0])

    # os.rename('%s\\%s.%s-win_%s.pyd' % (folder_path, filename, cpxx, amdxx), pyd_name)
    os.rename(amd64_pyd[0], pyd_name)  # 改名字，删除多余的cp38-win_amd64.等
    os.remove('%s.c' % filename)  # 删除临时文件
    build_folder_path = os.path.join(folder_path, 'build')
    shutil.rmtree(build_folder_path)  # 删除掉生成的build文件夹
    os.remove('setup.py')  # 删除掉生成的setup.py
    os.remove(file_path)


def get_all_file(path):  # 遍历此目录下的所有py文件，包含子目录里的py
    path = os.path.abspath(path)
    parent = os.path.dirname(path)
    build_folder_path = os.path.join(parent, 'build_src')
    if os.path.exists(build_folder_path): shutil.rmtree(build_folder_path)  # 删除build文件夹
    shutil.copytree(path, build_folder_path)
    for root, dirs, files in os.walk(build_folder_path):
        for name in files:
            if name.endswith(".py"):
                file_path = os.path.join(root, name)
                py2pyd(file_path)
            if name.endswith(".pyi") or name.endswith(".cpp"):
                os.remove(os.path.join(root, name))
        for dir_name in dirs:
            if dir_name == '__pycache__':
                dir_path = os.path.join(root, dir_name)
                shutil.rmtree(dir_path)
    os.chdir(parent)


# if len(sys.argv) <= 3:  # 判断命令行参数是否合法
#     print("\n命令行参数错误...\n");
#     sys.exit()

# one_all, del_py, paths = sys.argv[1:4]  # 获取命令行参数
if __name__ == '__main__':
    os.system("python build_c.py")
    if os.path.exists("main.exe"):
        os.remove("main.exe")
    paths = "./src"
    get_all_file(paths)
    os.system('pyinstaller -w -F --add-data "build_src/;src/" main.py')
    shutil.rmtree("build_src")
    shutil.rmtree("build")
    shutil.move("dist/main.exe", "main.exe")
    shutil.rmtree("dist")