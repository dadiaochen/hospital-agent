import os

print("=" * 60)
print("  📊 项目状态检查")
print("=" * 60)
print()

# 1. 检查目录结构
print("1️⃣  目录结构:")
key_dirs = ['backend/app/api', 'backend/app/services', 'backend/app/models', 
            'backend/app/agent', 'backend/app/tools', 'docs', 'frontend']
for d in key_dirs:
    status = "✅" if os.path.exists(d) else "❌"
    print(f"   {status} {d}")
print()

# 2. 检查 services 层
print("2️⃣  Services 层状态:")
services_dir = 'backend/app/services'
if os.path.exists(services_dir):
    files = [f for f in os.listdir(services_dir) if f.endswith('.py')]
    if len(files) == 1 and files[0] == '__init__.py':
        print("   ⚠️  services 层是空的（只有 __init__.py）")
        print("   💡 建议：创建 service 文件")
    else:
        print(f"   ✅ 有 {len(files)} 个 Python 文件")
print()

# 3. 检查模型文件
print("3️⃣  数据模型文件:")
models_dir = 'backend/app/models'
if os.path.exists(models_dir):
    files = [f for f in os.listdir(models_dir) if f.endswith('.py') and f != '__init__.py']
    print(f"   ✅ 共 {len(files)} 个模型文件")
    for f in files:
        print(f"      - {f}")
print()

# 4. 检查文档
print("4️⃣  文档状态:")
if os.path.exists('docs'):
    all_docs = [f for f in os.listdir('docs') if f.endswith('.md')]
    review_docs = [f for f in all_docs if 'REVIEW' in f.upper() or 'CODE_REVIEW' in f.upper()]
    print(f"   ✅ 总共 {len(all_docs)} 份文档")
    print(f"   📘 审查文档 {len(review_docs)} 份:")
    for d in review_docs:
        print(f"      - {d}")
print()

# 5. 检查配置文件
print("5️⃣  配置文件:")
config_files = ['.env.example', 'docker-compose.yml', 'alembic.ini', 
                'backend/requirements.txt', 'frontend/package.json']
for f in config_files:
    status = "✅" if os.path.exists(f) else "❌"
    print(f"   {status} {f}")
print()

# 6. 统计代码行数
print("6️⃣  代码统计:")
py_files = []
for root, dirs, files in os.walk('backend/app'):
    for file in files:
        if file.endswith('.py'):
            py_files.append(os.path.join(root, file))

total_lines = 0
for f in py_files:
    try:
        with open(f, 'r', encoding='utf-8') as file:
            total_lines += len(file.readlines())
    except:
        pass

print(f"   📝 Python 文件数: {len(py_files)}")
print(f"   📏 总代码行数: {total_lines}")
print()

print("=" * 60)
print("  ✅ 检查完成")
print("=" * 60)
