# SmartDocs - 智能文档问答平台

SmartDocs是一个企业级文档智能问答系统，可以帮助团队成员快速检索和查询文档内容。系统使用RAG（检索增强生成）技术，结合大语言模型，实现对企业文档内容的智能问答。

## 项目概览

### 核心功能
- 文档管理：上传、查看和删除PDF、Word、TXT等格式的文档
- 文档内容智能检索：基于向量数据库的文档内容检索
- 智能问答：与文档内容进行多轮上下文对话
- 用户管理：用户注册、登录和权限控制

### 技术栈
- **后端框架**: Django
- **API框架**: Django Ninja
- **数据库**: PostgreSQL
- **向量检索**: FAISS
- **大语言模型**: 通义千问/DashScope API
- **文档处理**: PyPDF2, python-docx等

## 项目结构

```
SmartDocs/
├── accounts/           # 用户账户相关功能
├── documents/          # 文档管理功能
├── qa/                 # 问答系统功能
├── smartdocs_project/  # 项目配置
└── manage.py           # Django管理脚本
```

## 开发指南

### 环境设置

1. 克隆仓库
```bash
git clone https://github.com/yourusername/SmartDocs.git
cd SmartDocs
```

2. 创建并激活虚拟环境
```bash
python -m venv .venv
source .venv/bin/activate  # Linux/Mac

3. 安装依赖
```bash
pip install -e .
```

4. 运行数据库迁移
```bash
python manage.py makemigrations
python manage.py migrate
```

5. 创建超级用户
```bash
python manage.py createsuperuser
```

6. 运行开发服务器
```bash
python manage.py runserver
```

### 待实现功能

1. **文档处理流程**
   - 实现文档解析和分块逻辑
   - 集成向量数据库(FAISS)
   - 完善文档上传和处理流程

2. **RAG系统**
   - 实现基于LangChain的RAG检索流程
   - 集成大语言模型API(DashScope/Qwen)
   - 优化检索准确性和响应速度

3. **用户界面**
   - 实现前端界面(可以使用Vue/React等)
   - 设计用户友好的交互流程
   - 实现实时对话功能

4. **部署与优化**
   - 配置PostgreSQL数据库
   - 优化性能和并发处理
   - 添加更多安全特性

## API文档

开发服务器运行后，可以在以下地址访问API文档：

- API文档: http://localhost:8000/api/docs
- 公开API文档: http://localhost:8000/public-api/docs

## 许可证

[MIT License](LICENSE)