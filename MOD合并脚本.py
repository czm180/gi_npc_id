# Author: SilentNightSound#7430
# Special Thanks:
#   Takoyaki#0697 (for demonstrating principle and creating the first proof of concept)
#   HazrateGolabi#1364 (for implementing the code to limit toggles to the on-screen character)

# V2.0 of Mod Merger/Toggle Creator Script

# Merges multiple mods into one, which can be toggled in-game by pressing a key

# USAGE: Run this script in a folder which contains all the mods you want to merge
# So if you want to merge mods CharA, CharB, and CharC put all 3 folders in the same folder as this script and run it

# This script will automatically search through all subfolders to find mod ini files.
# It will not use .ini if that ini path/name contains "disabled"

# NOTE: This script will only function on mods generated using the 3dmigoto GIMI plugin

import os
import re
import argparse
import hashlib

def main():
    parser = argparse.ArgumentParser(description="从几个mod文件夹生成合并的mod")
    parser.add_argument("-r", "--root", type=str,  default=".",  help="用于创建mod的位置")
    parser.add_argument("-s", "--store", action="store_true", help="用于在完成后保持原始.ini文件的启用状态")
    parser.add_argument("-e", "--enable", action="store_true", help="重新启用禁用的.ini文件")
    parser.add_argument("-n", "--name", type=str,  default="merged.ini", help="最终.ini文件的名称")
    parser.add_argument("-k", "--key", type=str, default="", help="按键切换模块")
    parser.add_argument("-c", "--compress",  action="store_true", help="使输出mods尽可能小（警告：难以回溯，请先备份）")
    parser.add_argument("-a", "--active", action="store_true",  default=True, help="交换时仅交换活动角色）")

    args = parser.parse_args()

    print("\n原神Mod 合并/切换 创建脚本           发布地址：https://gamebanana.com/tools/11165\n")

    if args.active:
        print("仅交换当前活跃（在屏幕上可见）的角色的设置")

    if args.enable:
        print("重新启用所有.ini文件")
        enable_ini(args.root)
        print()

    if not args.store:
        print("\n警告：一旦此脚本完成，它将禁用用于生成合并mod的所有.ini文件。（这是最终版本在没有冲突的情况下工作所必需的）")
        print("您可以使用-s标志来防止这种行为。")
        print("此脚本还可以使用-e标志-u重新启用当前文件夹和所有子文件夹中的所有mod，如果需要重新生成合并后的ini，请使用此标志。")

    if args.compress:
        print("\n警告2：-c/--compress选项使输出更小，但很难从合并的mod中检索原始mod。请确保有备份，并在确定一切正常后才考虑使用该选项。")

    print("\n正在搜索.ini文件")
    ini_files = collect_ini(args.root, args.name)

    if not ini_files:
        print("找不到.ini文件-请确保mod文件夹与此脚本位于同一文件夹中。")
        print("如果在一组已经是切换模式一部分的文件上使用此脚本，请使用-e启用.ini并重新生成合并ini")
        return

    print("\n找到：")
    for i, ini_file in enumerate(ini_files):
        print(f"\t{i}:  {ini_file}")

    print("\n脚本将使用上面列出的顺序合并。（0是mod开始的默认值，它将循环0,1,2,3,4,0,1…等等）")
    print("如果可以，请按 ENTER（回车）键。 如果希望改变mods合并顺序，请输入您希望的顺序。（例如：3 0 1 2）")
    print("如果输入的数字小于总数，则此脚本将只合并列出的数字。\n")
    ini_files = get_user_order(ini_files)

    if args.key:
        key = args.key
    else:
        print("\n请输入将用于循环mods的按键。（也可以使用-k标志输入，或稍后在.ini中设置）按键必须是单个字母\n")
        key = input()
        while not key or len(key) != 1:
            print("\n无法识别按键，它必须是单个字母。\n")
            key = input()
        key = key.lower()

    constants =    "; Constants ---------------------------\n\n"
    overrides =    "; Overrides ---------------------------\n\n"
    commands  =    "; CommandList -------------------------\n\n"
    resources =    "; Resources ---------------------------\n\n"

    swapvar = "swapvar"
    constants += f"[Constants]\nglobal persist ${swapvar} = 0\n"
    if args.active:
        constants += f"global $ActiveCharacter = 0\n"
    constants += f"\n[KeySwap]\n"
    if args.active:
        constants += f"condition = $ActiveCharacter == 1\n"
    constants += f"key = {key}\ntype = cycle\n${swapvar} = {','.join([str(x) for x in range(len(ini_files))])}\n\n"
    if args.active:
        constants += f"[Present]\npost $ActiveCharacter = 0\n\n"

    print("正在分析ini")
    all_mod_data = []
    ini_group = 0
    for ini_file in ini_files:
        with open(ini_file, "r", encoding="utf-8") as f:
            ini_text = ["["+x.strip() for x in f.read().split("[")]
            for section in ini_text[1:]:
                mod_data = parse_section(section)
                mod_data["location"] = os.path.dirname(ini_file)
                mod_data["ini_group"] = ini_group
                all_mod_data.append(mod_data)
        ini_group += 1

    print("计算覆盖和资源")
    command_data = {}
    seen_hashes = {}
    for i in range(len(all_mod_data)):
        # Overrides. Since we need these to generate the command lists later, need to store the data
        if "hash" in all_mod_data[i]:
            index = -1
            if "match_first_index" in all_mod_data[i]:
                index = all_mod_data[i]["match_first_index"]
            # First time we have seen this hash, need to add it to overrides
            if (all_mod_data[i]["hash"], index) not in command_data:
                command_data[(all_mod_data[i]["hash"], index)] = [all_mod_data[i]]
                overrides += f"[{all_mod_data[i]['header']}{all_mod_data[i]['name']}]\nhash = {all_mod_data[i]['hash']}\n"
                if index != -1:
                    overrides += f"match_first_index = {index}\n"
                # These are custom commands GIMI implements, they do not need a corresponding command list
                if "VertexLimitRaise" not in all_mod_data[i]["name"]:
                    overrides += f"run = CommandList{all_mod_data[i]['name']}\n"
                if args.active:
                    if "Position" in all_mod_data[i]["name"]:
                        overrides += f'$ActiveCharacter = 1\n'
                overrides += "\n"
            # Otherwise, we have seen the hash before and we just need to append it to the commandlist
            else:
                command_data[(all_mod_data[i]["hash"], index)].append(all_mod_data[i])

        # Resources
        elif "filename" in all_mod_data[i]:
            resources += f"[{all_mod_data[i]['header']}{all_mod_data[i]['name']}.{all_mod_data[i]['ini_group']}]\n"
            for command in all_mod_data[i]:
                if command in ["header", "name", "location", "ini_group"]:
                    continue
                if command == "filename":
                    with open(f"{all_mod_data[i]['location']}\\{all_mod_data[i][command]}", "rb") as f:
                        sha1 = hashlib.sha1(f.read()).hexdigest()
                    if sha1 in seen_hashes and args.compress:
                        resources += f"{command} = {seen_hashes[sha1]}\n"
                        os.remove(f"{all_mod_data[i]['location']}\\{all_mod_data[i][command]}")
                    else:
                        seen_hashes[sha1] = f"{all_mod_data[i]['location']}\\{all_mod_data[i][command]}"
                        resources += f"{command} = {all_mod_data[i]['location']}\\{all_mod_data[i][command]}\n"
                else:
                    resources += f"{command} = {all_mod_data[i][command]}\n"
            resources += "\n"


    print("构建命令列表")
    for hash, index in command_data:
        if "VertexLimitRaise" in command_data[(hash, index)][0]["name"]:
            continue
        commands += f"[CommandList{command_data[(hash, index)][0]['name']}]\nif "
        for model in command_data[(hash, index)]:
            commands += f"${swapvar} == {model['ini_group']}\n"
            for command in model:
                if command in ["header", "name", "hash", "match_first_index", "location", "ini_group"]:
                    continue
                commands += f"\t{command} = {model[command]}"
                if command[:2] in ["vb", "ib", "ps", "vs", "th"]:
                    commands += f".{model['ini_group']}"
                commands += "\n"
            commands += "else if "
        commands = commands.rsplit("else if",1)[0] + "endif\n\n"

    print("打印结果")
    result = f"; Merged Mod: {', '.join([x for x in ini_files])}\n\n"
    result += constants
    result += overrides
    result += commands
    result += resources
    result += "\n\n; .ini generated by GIMI (Genshin-Impact-Model-Importer) mod merger script\n"
    result += "; If you have any issues or find any bugs, please open a ticket at https://github.com/SilentNightSound/GI-Model-Importer/issues or contact SilentNightSound#7430 on discord"

    with open(args.name, "w", encoding="utf-8") as f:
        f.write(result)

    if not args.store:
        print("清理和禁用ini")
        for file in ini_files:
            os.rename(file, os.path.join(os.path.dirname(file), "DISABLED") + os.path.basename(file))


    print("所有操作已完成")


# Collects all .ini files from current folder and subfolders
def collect_ini(path, ignore):
    ini_files = []
    for root, dir, files in os.walk(path):
        if "disabled" in root.lower():
            continue
        for file in files:
            if "disabled" in file.lower() or ignore.lower() in file.lower():
                continue
            if os.path.splitext(file)[1] == ".ini":
                ini_files.append(os.path.join(root, file))
    return ini_files

# Re-enables disabled ini files
def enable_ini(path):
    for root, dir, files in os.walk(path):
        for file in files:
            if os.path.splitext(file)[1] == ".ini" and ("disabled" in root.lower() or "disabled" in file.lower()):
                print(f"\t重新启用 {os.path.join(root, file)}")
                new_path = re.compile("disabled", re.IGNORECASE).sub("", os.path.join(root, file))
                os.rename(os.path.join(root, file), new_path)


# Gets the user's preferred order to merge mod files
def get_user_order(ini_files):

    choice = input()

    # User entered data before pressing enter
    while choice:
        choice = choice.strip().split(" ")

        if len(choice) > len(ini_files):
            print("\n错误：无法输入超过原始MOD数量的数字\n")
            choice = input()
        else:
            try:
                result = []
                choice = [int(x) for x in choice]
                if len(set(choice)) != len(choice):
                    print("\n错误：请最多输入一次每个MOD被赋予的数字\n")
                    choice = input()
                elif max(choice) >= len(ini_files):
                    print("\n错误：所选索引大于可用的最大索引\n")
                    choice = input()
                elif min(choice) < 0:
                    print("\n错误：所选索引小于0\n")
                    choice = input()
                    print()
                else:
                    for x in choice:
                        result.append(ini_files[x])
                    return result
            except ValueError:
                print("\n错误：请只输入要合并的mods的索引，用空格分隔（例如：3 0 1 2）\n")
                choice = input()

    # User didn't enter anything and just pressed enter
    return ini_files


# Parses a section from the .ini file
def parse_section(section):
    mod_data = {}
    recognized_header = ("[TextureOverride", "[ShaderOverride", "[Resource")
    for line in section.splitlines():
        if not line.strip() or line[0] == ";":  # comments and empty lines
            continue

        # [] lines
        for header in recognized_header:
            if header in line:
                mod_data["header"] = header[1:]
                mod_data["name"] = line.split(header)[1][:-1]
                break

        # All other lines
        if "=" in line:
            key, data = line.split("=")
            mod_data[key.strip()] = data.strip()

    return mod_data


if __name__ == "__main__":
    main()