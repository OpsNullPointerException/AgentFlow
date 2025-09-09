# AgentFlow 智能代理平台

AgentFlow是一个基于LangChain的智能agent平台，集成了文档管理、智能问答、任务自动化等多种AI能力。

## 🌟 核心功能

### 1. 智能agent系统
- **多种Agent类型**：ReAct、OpenAI Functions、结构化聊天等
- **丰富工具集成**：文档搜索、计算器、Python执行器、网络搜索
- **智能记忆管理**：缓冲窗口、摘要压缩等多种记忆策略
- **任务自动化**：自动分解复杂任务并执行

### 2. 文档智能管理
- **多格式支持**：PDF、Word、TXT等文档上传
- **向量化存储**：基于FAISS的高效检索
- **智能问答**：基于RAG的文档问答系统
- **语义搜索**：支持重排序的文档检索

### 3. 用户管理系统
- **JWT认证**：安全的用户认证体系
- **API密钥管理**：支持API访问控制
- **权限隔离**：用户数据完全隔离

### 4. 完整API生态
- **RESTful API**：标准化的API接口
- **实时监控**：执行过程追踪和性能分析
- **扩展性强**：模块化设计，易于扩展新功能

## 🛠️ 技术栈

- **后端框架**：Django + Django Ninja
- **AI框架**：LangChain
- **大语言模型**：阿里云千问 (Qwen/DashScope)
- **向量数据库**：FAISS
- **数据库**：PostgreSQL（无外键设计）
- **前端**：Vue.js + Element Plus
- **部署**：Docker + Docker Compose

## 🚀 应用场景

1. **智能助手**：结合多种工具的综合性AI助手
2. **文档问答**：企业知识库智能问答系统
3. **数据分析**：自动化数据处理和分析
4. **任务自动化**：复杂业务流程的智能化处理
5. **代码助手**：编程相关的智能辅助工具

## 📁 项目结构

```
AgentFlow/
├── agents/           # 智能代理模块
├── documents/        # 文档管理模块
├── qa/              # 问答系统模块
├── accounts/        # 用户管理模块
├── common/          # 公共工具模块
├── frontend/        # 前端界面
└── deploy/          # 部署配置
```

## 🔧 快速开始

### 环境准备
```bash
# 安装依赖
pip install -r requirements.txt

# 配置环境变量
cp .env.example .env
# 编辑 .env 文件，配置API密钥等

# 数据库迁移
python manage.py migrate

# 启动服务
python manage.py runserver
```

### Docker部署
```bash
# 使用Docker Compose启动
cd deploy
docker-compose up -d
```

## 📚 API文档

启动服务后访问：
- API文档：http://localhost:8000/api/docs
- 管理后台：http://localhost:8000/admin
- 前端界面：http://localhost:8000
