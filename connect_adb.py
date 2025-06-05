# deepseek写的懒得修了
# 适配MuMuPlayer-12.0
import json
import psutil
import os
import subprocess


def find_mumu_processes():
    """查找所有 MuMu 模拟器进程"""
    processes = []
    for proc in psutil.process_iter(["pid", "name", "exe", "cmdline"]):
        # 适配不同版本的 MuMu 进程名（如 NemuHeadless.exe）
        if proc.info["name"] in ["MuMuPlayer.exe"]:
            processes.append(proc.info)
    return processes


def get_vm_name(cmdline):
    """从命令行参数获取虚拟机名称"""
    try:
        index = cmdline.index("-v")
        return "MuMuPlayer-12.0-" + cmdline[index + 1]
    except (ValueError, IndexError):
        return "MuMuPlayer-12.0-0"


def get_installation_dir(exe_path):
    """从可执行路径推导安装目录"""
    try:
        path_parts = exe_path.split(os.sep)
        # 查找关键路径节点（适配不同版本路径结构）
        for key in ["MuMuPlayer-12.0","MuMu Player 12"]:
            if key in path_parts:
                key_index = path_parts.index(key)
                return os.sep.join(path_parts[: key_index + 1])
        return None
    except Exception:
        return None


# D:\workTools\MuMuPlayer-12.0\vms\MuMuPlayer-12.0-2\configs
def get_adb_port(installation_dir, vm_name):
    """从虚拟机配置文件中获取 ADB 端口"""
    try:
        # 尝试多种可能的配置文件路径
        conf_path = os.path.join(
            installation_dir, "vms", vm_name, "configs", "vm_config.json"
        )

        if os.path.exists(conf_path):
            with open(conf_path, "r") as f:
                conf = json.loads(f.read())
                adb_conf = conf["vm"]["nat"]["port_forward"]["adb"]
                port = adb_conf["host_port"]
                return int(port)
        return None
    except Exception as e:
        return None


def connect_adb(installation_dir, port):
    """使用模拟器自带的 ADB 进行连接"""
    try:
        # 尝试多个可能的 ADB 路径
        adb_paths = [os.path.join(installation_dir, "shell", "adb.exe"), "adb"]

        for adb_path in adb_paths:
            if os.path.exists(adb_path):
                result = subprocess.check_output(
                    f"{adb_path} connect 127.0.0.1:{port}",
                    shell=True,
                    stderr=subprocess.STDOUT,
                )
                return result.decode().encode("utf-8").decode("utf-8")
        return None
    except Exception:
        return None


def get_connected_port():  # 获取已连接的 ADB 端口
    result = subprocess.check_output(
        "adb devices",
        shell=True,
        stderr=subprocess.STDOUT,
    )
    ports = []
    for line in result.decode().encode("utf-8").decode("utf-8").splitlines():
        if line.startswith("127.0.0.1:"):
            port = line.split("\t")[0].split(":")[1]
            ports.append(int(port))
    return ports

def restart_adb():
    subprocess.call("adb kill-server", shell=True)
    subprocess.call("adb start-server", shell=True)


def main():
    restart_adb()
    print("正在扫描 MuMu 模拟器进程...")
    processes = find_mumu_processes()

    if not processes:
        print("未找到正在运行的 MuMu 模拟器进程")
        return

    print(f"发现 {len(processes)} 个 MuMu 进程")

    connected_ports = get_connected_port()
    for proc in processes:
        try:
            print(f"\n处理进程 PID: {proc['pid']}")

            # 获取虚拟机名称
            vm_name = get_vm_name(proc["cmdline"])
            if not vm_name:
                print("无法获取虚拟机名称，跳过")
                continue
            print(f"虚拟机名称: {vm_name}")

            # 获取安装目录
            exe_path = proc["exe"]
            install_dir = get_installation_dir(exe_path)
            if not install_dir:
                print("无法确定安装目录，跳过")
                continue
            print(f"安装目录: {install_dir}")

            # 获取 ADB 端口
            port = get_adb_port(install_dir, vm_name)
            if not port:
                print("无法获取 ADB 端口，跳过")
                continue
            if port in connected_ports:
                print(f"端口 {port} 已连接，跳过")
                continue

            print(f"尝试连接 ADB 端口: {port}")

            # 执行 ADB 连接
            result = connect_adb(install_dir, port)
            if not result:
                print("ADB 连接失败")
                continue

            print("ADB 连接结果:")
            print(result)
            if "connected" in result:
                connected_ports = get_connected_port()
                print("连接成功!")
            else:
                print(f"连接失败: {result}")

        except Exception as e:
            print(f"处理异常: {str(e)}")
            continue

    print("\n连接完成，已连接的 ADB 端口:")
    print(
        "\n".join(list(map(lambda x: str(x), connected_ports)))
        if connected_ports
        else "无成功连接"
    )


if __name__ == "__main__":
    main()
