# 周易八卦

本项目是一个基于Flask的Web应用，用于生成和展示周易八卦卦象。

## 项目结构

- `index.html`：前端页面，包含展示卦象的HTML和CSS代码。
- `get_hexagram.py`：后端代码，使用Flask框架提供API接口生成卦象。

## 使用方法

### 前端

1. 打开`index.html`文件。
2. 点击“开始算卦”按钮，页面将会通过API请求生成一个新的卦象并展示。

### 后端

1. 安装Flask：
  ```bash
  pip install Flask
  ```
2. 运行`get_hexagram.py`：
  ```bash
  python get_hexagram.py
  ```
3. 后端服务将会在`http://127.0.0.1:5000`启动。

## API

### 获取卦象

- **URL**：`/api/getHexagram`
- **方法**：`GET`
- **响应**：
  ```json
  {
    "results": ["阳", "阴", "阳", "阴", "阳", "阴"],
    "hexagramName": "上乾下坤"
  }
  ```

## 贡献

欢迎提交Pull Request或报告问题。

## 许可证

本项目使用MIT许可证。
