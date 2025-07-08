import pandas as pd
import sqlite3
import openpyxl
import os
from openpyxl.utils import get_column_letter

excel_file = 'output.xlsx'  # Excel 文件名
output_img_dir = 'static/images'
os.makedirs(output_img_dir, exist_ok=True)

# 读取Excel数据（包含原始帖子链接）
df = pd.read_excel(excel_file)

# 保证“价格”为数字类型，无法转换的设为NaN
df['价格'] = pd.to_numeric(df['价格'], errors='coerce')

# 删除价格为空的行
df = df.dropna(subset=['价格']).reset_index(drop=True)

# 保证图片列为字符串类型（避免 SettingWithCopy 警告）
for col_name in ['图片1', '图片2', '图片3']:
    df[col_name] = df[col_name].astype('object')

# 读取Excel嵌入图片
wb = openpyxl.load_workbook(excel_file)
ws = wb.active

# 提取嵌入图片并保存，构建 映射：单元格 → 图片路径
img_map = {}
for image in ws._images:
    if not hasattr(image, 'anchor') or not hasattr(image.anchor, '_from'):
        continue
    anchor = image.anchor._from
    col_letter = get_column_letter(anchor.col + 1)
    row_num = anchor.row + 1
    cell = f"{col_letter}{row_num}"

    img_path = os.path.join(output_img_dir, f"{cell}.png")
    img_bytes = image._data()
    with open(img_path, 'wb') as f:
        f.write(img_bytes)
    img_map[cell] = f"/static/images/{cell}.png"

# 把图片路径写回 DataFrame 中
for idx in df.index:
    row_num = idx + 2  # Excel数据从第2行起
    for col_name, col_letter in [('图片1', 'F'), ('图片2', 'G'), ('图片3', 'H')]:
        cell = f"{col_letter}{row_num}"
        df.at[idx, col_name] = img_map.get(cell, '')

# ✅ SQLite写入：包含“帖子链接”列
conn = sqlite3.connect('data.db')
df.to_sql('data', conn, if_exists='replace', index=False)
conn.close()

print("✅ Excel内容和图片链接成功导入到 SQLite，包括原始帖子链接！")
