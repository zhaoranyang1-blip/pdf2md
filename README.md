# PDF → Markdown

一个本地运行的 PDF 转 Markdown 网页工具，使用 PyMuPDF 提取文本，并根据字号尝试识别标题、项目符号和编号列表。默认会尝试把可读取的数学符号、Unicode 上下标和 PDF 中通过文字位置表示的上下标转换为 `$...$` 包裹的 LaTeX；网页可以关闭公式转换。

## 运行

```bash
python -m venv .venv
.venv\Scripts\activate   # macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
python app.py
```

打开 http://127.0.0.1:5000，拖入 PDF 即可转换并下载 `.md` 文件。

## 部署成公网网页

最简单的方式是使用 Render：将这个项目上传到 GitHub，在 Render 中选择 **New → Web Service**，连接该仓库。Render 会读取 `render.yaml`，自动安装依赖并启动服务，部署完成后会生成一个可分享的 `https://...onrender.com` 地址。也可以在 Railway 等平台使用同样的启动命令：`gunicorn app:app`。

扫描版 PDF 需要先经过 OCR；当前版本针对可复制文本的 PDF。公式转换是基于文本和排版位置的启发式处理，能保留和转换常见符号及上下标，但不能识别图片公式，也不能可靠重建复杂分式、矩阵、根式布局。复杂公式请校对转换结果。
