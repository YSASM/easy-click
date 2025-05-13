"""
c构建程序
先将c文件编译成pyd
"""
import glob
import regex
import os, shutil
def extract_functions(c_file):
    # index = clang.cindex.Index.create()
    # tu = index.parse(c_file)
    functions = []
    c_file_content = ""
    with open(c_file, 'r') as f:
        c_file_content = f.read()
    func_pattern = regex.compile(r'((?:\b\w+\b|[*&]|\s+|<[^<>]*>|::)+)\s*(\w+(?:::\w+)*)\s*(\((?:[^()]*|(?0))*\))\s*(\{(?:[^{}]*|(?4))*\})', flags=regex.DOTALL)
    for match in func_pattern.finditer(c_file_content):
        # Extract function details
        return_type = match.group(1).strip()
        func_name = match.group(2).strip()
        params = match.group(3).strip('()').strip().split(',')
        functions.append({
            "name": func_name,
            "params": params,
            "return_type": return_type,
        })
    return functions
def format_type(type:str):
    type = type.replace("const ", "").replace("&", "").replace("*", "").split(" ")[0]
    if type == "std::string":
        return "str"
    elif type == "int" or type == "long" or type == "long long":
        return "int"
    elif type == "float" or type == "double":
        return "float"
    elif type == "bool":
        return "bool"
    elif "std::vector" in type:
        inner_type = format_type(type.split("<")[1].split(">")[0])
        return f"list[{inner_type}]"
    elif type.startswith("py::"):
        return type.replace("py::", "")
    else:
        return "Any"
def generate_pybind11_code(functions, c_file):
    code = """{c_file}
PYBIND11_MODULE({module_name}, m) {{
    m.doc() = "Auto-generated bindings";
    {bindings}
}}
    """.strip()
    setup = """
from setuptools import setup
from pybind11.setup_helpers import Pybind11Extension

ext_modules = [
    Pybind11Extension(
        "{module_name}",
        ["{output_file}"],  # Sort source files for reproducibility
    ),
]

setup(name="{module_name}", ext_modules=ext_modules)
        """.strip()
    output_file = c_file.replace(".cpp","_bind.cpp").replace("\\", "/")
    setup_file = os.path.dirname(c_file) +"\\setup.py".replace("\\", "/")
    folder_path = os.path.dirname(c_file)
    pyi_file = c_file.replace(".cpp",".pyi").replace("\\", "/")
    with open(c_file, 'r') as f:
        c_file_content = f.read()
        bindings = []
        pyi = []
        module_name = c_file.replace(os.path.dirname(c_file) + "\\", "").split('.')[0]
        for func in functions:
            for i,p in enumerate(func['params']):
                func['params'][i] = f"args{i}:{format_type(p)}"
            params = ', '.join(func['params'])
            pyi_line = f'def {func["name"]}({params}): {format_type(func["return_type"])}'
            pyi.append(pyi_line)
            bind_line = f'm.def("{func["name"]}", &{func["name"]}, "Auto-binding for {func["name"]}");'
            bindings.append(bind_line)
        code = code.format(
            c_file=c_file_content,
            module_name=module_name,
            bindings='\n    '.join(bindings))
    with open(pyi_file, 'w') as f:
        f.write("\n".join(pyi))
    with open(output_file, 'w') as f:
        f.write(code)
    setup = setup.format(module_name=module_name,output_file=output_file)
    with open(setup_file, 'w') as f:
        f.write(setup)
    os.chdir(folder_path)
    os.system('python setup.py build_ext --inplace --build-lib ' + folder_path)  # py编译开始
    pyd_name = '%s\\%s.pyd' % (folder_path, module_name)  # pyd文件名
    if os.path.exists(pyd_name): os.remove(pyd_name)  # 删除老的pyd
    amd64_pyd = glob.glob(module_name + "*.pyd")  # 获取pyd文件的全名，类似***.cp38-win_amd64.pyd
    print("生成了PYD：" + amd64_pyd[0])
    os.rename(amd64_pyd[0], pyd_name)  # 改名字，删除多余的cp38-win_amd64.等
    os.remove(output_file)  # 删除临时文件
    build_folder_path = os.path.join(folder_path, 'build')
    shutil.rmtree(build_folder_path)  # 删除掉生成的build文件夹
    os.remove('setup.py')  # 删除掉生成的setup.py




def get_all_file(path):  # 遍历此目录下的所有py文件，包含子目录里的py
    cwd = os.getcwd()
    path = os.path.abspath(path)
    parent = os.path.dirname(path)
    build_folder_path = os.path.join(parent, 'src')
    for root, dirs, files in os.walk(build_folder_path):
        for name in files:
            if name.endswith(".cpp") and not name.endswith("_bind.cpp"):
                file_path = os.path.join(root, name)
                functions = extract_functions(file_path)
                generate_pybind11_code(functions, file_path)
    os.chdir(cwd)


# if len(sys.argv) <= 3:  # 判断命令行参数是否合法
#     print("\n命令行参数错误...\n");
#     sys.exit()

# one_all, del_py, paths = sys.argv[1:4]  # 获取命令行参数
if __name__ == '__main__':
    paths = "./src"
    get_all_file(paths)