# SmartDocs 智能文档问答平台

SmartDocs是一个企业/团队文档的智能问答系统，可以上传文档，通过大模型进行智能问答。

## 功能特点

- 上传文档（PDF、Word、txt）
- LLM 问答（支持多轮上下文记忆）
- 知识库检索（RAG）
- 后台管理（Django Admin）
- 用户登录/注册（JWT/Auth）

## 技术栈

- **后端框架**：Django
- **API框架**：Django REST Framework
- **大模型集成**：LangChain
- **大语言模型**：Qwen/DashScope (阿里云千问)
- **向量数据库**：FAISS（用于文档检索）
- **数据库**：PostgreSQL（无外键设计）

## 项目结构

```
SmartDocs/
├── accounts/              # 用户账户应用
│   ├── models/            # 用户模型
│   ├── schemas/           # 数据模式
│   ├── controllers/       # API控制器
│   └── services/          # 业务逻辑服务
├── documents/             # 文档管理应用
│   ├── models/            # 文档模型
│   ├── schemas/           # 数据模式
│   ├── controllers/       # API控制器
│   └── services/          # 文档处理服务
├── qa/                    # 问答应用
│   ├── models/            # 问答模型
│   ├── schemas/           # 数据模式
│   ├── controllers/       # API控制器
│   └── services/          # 问答服务
├── common/                # 共享组件
├── vector_store/          # 向量存储目录
└── smartdocs_project/     # 项目配置
```

## 环境配置

### 1. 安装依赖

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac

# 安装依赖
pip install -e .
```

### 2. 环境变量配置

在项目根目录创建`.env`文件：

```ini
# Django 配置
DEBUG=True
SECRET_KEY=your-secret-key

# 数据库配置
DB_NAME=smartdocs
DB_USER=your-db-user
DB_PASSWORD=your-db-password
DB_HOST=localhost
DB_PORT=5432

# 千问API配置
DASHSCOPE_API_KEY=your_dashscope_api_key_here

# 向量库配置
VECTOR_STORE_PATH=./vector_store

# 上传文件配置
MAX_UPLOAD_SIZE=10485760  # 10MB
```

### 3. 数据库设置

```bash
# 创建迁移
python manage.py makemigrations

# 应用迁移
python manage.py migrate

# 创建超级用户
python manage.py createsuperuser
```

### 4. 运行开发服务器

```bash
python manage.py runserver
```

## API接口

### 文档管理

- `POST /api/documents/upload/` - 上传文档
- `GET /api/documents/list/` - 获取文档列表
- `GET /api/documents/{id}/` - 获取文档详情

### 问答系统

- `POST /api/qa/ask/` - 提问
- `GET /api/qa/conversations/` - 获取对话列表
- `GET /api/qa/conversations/{id}/` - 获取对话详情

### 用户管理

- `POST /api/auth/register/` - 注册
- `POST /api/auth/login/` - 登录
- `GET /api/auth/me/` - 获取当前用户信息

## 注意事项

- 本项目使用了阿里云千问大模型，需要有效的API密钥
- 为提高性能，数据库设计采用无外键约束的方式
- 上传的文档会被分块并存储为向量，以便快速检索