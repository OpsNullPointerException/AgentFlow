// 创建Vue应用
const { createApp, ref, reactive, onMounted, nextTick, watch } = Vue;

// 确保Element Plus全局可用
const ElementPlus = window.ElementPlus;
const { ElMessage, ElMessageBox } = ElementPlus;

// 设置API基础路径
const API_BASE_URL = '';

const app = createApp({
    setup() {
        // 身份验证状态
        const isLoggedIn = ref(false);
        const token = ref(localStorage.getItem('token') || '');
        const userInfo = ref({});
        const loading = ref(false);
        const activeTab = ref('login');
        const activeMainTab = ref('agents');
        
        // 登录表单
        const loginForm = reactive({
            username: '',
            password: ''
        });
        
        // 注册表单
        const registerForm = reactive({
            username: '',
            password: '',
            confirmPassword: ''
        });
        
        // 对话相关
        const conversations = ref([]);
        const selectedConversation = ref(null);
        const conversationMessages = ref([]);
        const currentMessage = ref('');
        const messages = ref([]);
        const newMessage = ref('');
        const sendingMessage = ref(false);
        const useStreamingMode = ref(true);
        const currentStreamingMessage = ref(null);
        const selectedModel = ref('qwen-turbo');
        const newConversationDialogVisible = ref(false);
        const newConversationTitle = ref('');
        const userScrolling = ref(false);
        const showScrollToBottom = ref(false);
        
        // 可用的模型选项
        const modelOptions = [
            { value: 'qwen-turbo', label: '千问Turbo (快速)' },
            { value: 'qwen-plus', label: '千问Plus (平衡)' },
            { value: 'qwen-max', label: '千问MAX (高质量)' }
        ];
        
        // 文档相关
        const documents = ref([]);
        const uploadDialogVisible = ref(false);
        const uploading = ref(false);
        const uploadForm = reactive({
            title: '',
            description: '',
            file: null
        });
        
        // 文档分页
        const documentPagination = reactive({
            page: 1,
            pageSize: 10,
            total: 0,
            totalPages: 0,
            hasNext: false,
            hasPrevious: false
        });
        
        // 搜索相关
        const searchQuery = ref('');
        const searchResults = ref([]);
        const searching = ref(false);
        
        // 文档详情对话框相关
        const documentDetailVisible = ref(false);
        const selectedDocumentDetail = ref(null);
        const loadingDocumentDetail = ref(false);
        
        // 智能体相关
        const agents = ref([]);
        const selectedAgent = ref(null);
        const agentExecutions = ref([]);
        const agentInput = ref('');
        const executingAgent = ref(false);
        const agentListKey = ref(0); // 用于强制重新渲染agent列表
        
        // 创建智能体
        const showCreateAgentDialog = ref(false);
        const creatingAgent = ref(false);
        const createAgentForm = reactive({
            name: '',
            description: '',
            agent_type: 'react',
            available_tools: ['document_search'],
            system_prompt: '你是一个智能助手，可以使用各种工具来帮助用户完成任务。'
        });
        
        // HTTP客户端
        const http = axios.create({
            baseURL: API_BASE_URL
        });
        
        // 请求拦截器，添加token
        http.interceptors.request.use(config => {
            if (token.value) {
                config.headers.Authorization = `Bearer ${token.value}`;
            }
            return config;
        }, error => {
            return Promise.reject(error);
        });
        
        // 响应拦截器，处理401错误
        http.interceptors.response.use(response => {
            return response;
        }, error => {
            if (error.response && error.response.status === 401) {
                handleLogout();
            }
            return Promise.reject(error);
        });
        
        // 初始化应用
        onMounted(async () => {
            console.log('🚀 应用初始化开始...');
            console.log('🚀 当前token:', token.value ? '存在' : '不存在');
            
            if (token.value) {
                try {
                    console.log('🚀 开始获取用户信息...');
                    // 获取用户信息
                    const response = await http.get('/api/accounts/me');
                    userInfo.value = response.data;
                    isLoggedIn.value = true;
                    console.log('🚀 用户信息获取成功:', userInfo.value);
                    
                    // 加载对话、文档和智能体
                    console.log('🚀 开始加载所有数据...');
                    const results = await Promise.allSettled([
                        loadConversations(),
                        loadDocuments(),
                        loadAgents()
                    ]);
                    
                    console.log('🚀 数据加载结果:', results);
                    
                    // 确保数据正确设置
                    console.log('🚀 初始化完成后，agents.value:', agents.value);
                    console.log('🚀 初始化完成后，conversations.value:', conversations.value);
                    console.log('🚀 初始化完成后，documents.value:', documents.value);
                    
                    setupScrollListener();
                    
                    // 页面初始化后滚动到底部
                    setTimeout(() => {
                        console.log('🚀 页面初始化 - 尝试滚动到底部');
                        scrollToBottom();
                    }, 500);
                } catch (error) {
                    console.error('🚀 获取用户信息失败', error);
                    handleLogout();
                }
            } else {
                // 用户未登录，显示登录界面
                console.log('🚀 用户未登录，显示登录界面');
                isLoggedIn.value = false;
            }
        });
        
        // 格式化日期
        const formatDate = (dateString) => {
            const date = new Date(dateString);
            const now = new Date();
            const diffDays = Math.floor((now - date) / (1000 * 60 * 60 * 24));
            
            if (diffDays === 0) {
                return date.toLocaleTimeString('zh-CN', { hour: '2-digit', minute: '2-digit' });
            } else if (diffDays === 1) {
                return '昨天';
            } else if (diffDays < 7) {
                return `${diffDays}天前`;
            } else {
                return date.toLocaleDateString('zh-CN', { month: '2-digit', day: '2-digit' });
            }
        };
        
        // 登录处理
        const handleLogin = async () => {
            if (!loginForm.username || !loginForm.password) {
                ElMessage.warning('请输入用户名和密码');
                return;
            }
            
            loading.value = true;
            try {
                const response = await axios.post('/public-api/accounts/login', loginForm);
                token.value = response.data.access_token;
                localStorage.setItem('token', token.value);
                
                // 获取用户信息
                const userResponse = await http.get('/api/accounts/me');
                userInfo.value = userResponse.data;
                isLoggedIn.value = true;
                
                // 加载数据
                await loadConversations();
                await loadDocuments();
                await loadAgents();
                
                ElMessage.success('登录成功');
            } catch (error) {
                console.error('登录失败', error);
                ElMessage.error(error.response?.data?.detail || '登录失败，请检查用户名和密码');
            } finally {
                loading.value = false;
            }
        };
        
        // 注册处理
        const handleRegister = async () => {
            if (!registerForm.username || !registerForm.password) {
                ElMessage.warning('请输入用户名和密码');
                return;
            }
            
            if (registerForm.password !== registerForm.confirmPassword) {
                ElMessage.warning('两次输入的密码不一致');
                return;
            }
            
            loading.value = true;
            try {
                await axios.post('/public-api/accounts/register', {
                    username: registerForm.username,
                    password: registerForm.password,
                    email: registerForm.username + '@example.com'
                });
                
                ElMessage.success('注册成功，请登录');
                activeTab.value = 'login';
                loginForm.username = registerForm.username;
                loginForm.password = '';
                
                // 清空注册表单
                registerForm.username = '';
                registerForm.password = '';
                registerForm.confirmPassword = '';
            } catch (error) {
                console.error('注册失败', error);
                ElMessage.error(error.response?.data?.detail || '注册失败');
            } finally {
                loading.value = false;
            }
        };
        
        // 退出登录
        const handleLogout = () => {
            token.value = '';
            localStorage.removeItem('token');
            isLoggedIn.value = false;
            userInfo.value = {};
            conversations.value = [];
            selectedConversation.value = null;
            messages.value = [];
            documents.value = [];
            agents.value = [];
            selectedAgent.value = null;
        };
        
        // 加载对话列表
        const loadConversations = async () => {
            try {
                console.log('💬 开始加载对话列表...');
                const response = await http.get('/api/qa/conversations');
                console.log('💬 对话API响应:', response.data);
                console.log('💬 对话数据类型:', typeof response.data);
                console.log('💬 对话数据是否为数组:', Array.isArray(response.data));
                console.log('💬 对话数据长度:', response.data?.length);
                
                conversations.value = response.data;
                console.log('💬 设置conversations.value为:', conversations.value);
                
                return true;
            } catch (error) {
                console.error('💬 获取对话列表失败', error);
                conversations.value = [];
                if (error.response && error.response.status === 401) {
                    console.log('💬 未授权访问，需要登录');
                    handleLogout();
                } else {
                    ElMessage.error('获取对话列表失败');
                }
                return false;
            }
        };
        
        // 加载文档列表
        const loadDocuments = async (page = 1, pageSize = 10) => {
            try {
                console.log('📄 开始加载文档列表...', { page, pageSize });
                const response = await http.get('/api/documents', {
                    params: {
                        page: page,
                        page_size: pageSize
                    }
                });
                
                console.log('📄 文档API响应:', response.data);
                console.log('📄 响应数据类型:', typeof response.data);
                console.log('📄 是否为数组:', Array.isArray(response.data));
                console.log('📄 是否有documents字段:', response.data && 'documents' in response.data);
                
                // 检查响应数据结构并适配
                if (response.data && typeof response.data === 'object' && 'documents' in response.data) {
                    // 新的分页格式
                    console.log('📄 使用新的分页格式');
                    documents.value = response.data.documents || [];
                    documentPagination.page = response.data.page || 1;
                    documentPagination.pageSize = response.data.page_size || 10;
                    documentPagination.total = response.data.total || 0;
                    documentPagination.totalPages = response.data.total_pages || 1;
                    documentPagination.hasNext = response.data.has_next || false;
                    documentPagination.hasPrevious = response.data.has_previous || false;
                } else if (Array.isArray(response.data)) {
                    // 旧的直接数组格式
                    console.log('📄 使用旧的数组格式');
                    documents.value = response.data;
                    documentPagination.page = 1;
                    documentPagination.pageSize = response.data.length;
                    documentPagination.total = response.data.length;
                    documentPagination.totalPages = 1;
                    documentPagination.hasNext = false;
                    documentPagination.hasPrevious = false;
                } else {
                    console.warn('📄 意外的API响应格式:', response.data);
                    console.warn('📄 将documents设置为空数组');
                    documents.value = [];
                    // 重置分页信息
                    documentPagination.page = 1;
                    documentPagination.pageSize = pageSize;
                    documentPagination.total = 0;
                    documentPagination.totalPages = 0;
                    documentPagination.hasNext = false;
                    documentPagination.hasPrevious = false;
                }
                
                console.log('📄 文档加载完成:', {
                    documentsCount: documents.value.length,
                    documentsArray: documents.value,
                    pagination: documentPagination
                });
                
                return true;
            } catch (error) {
                console.error('📄 获取文档列表失败', error);
                documents.value = [];
                if (error.response && error.response.status === 401) {
                    console.log('📄 未授权访问，需要登录');
                    handleLogout();
                } else {
                    ElMessage.error('获取文档列表失败');
                }
                return false;
            }
        };
        
        // 处理文档页面切换
        const handleDocumentPageChange = (newPage) => {
            loadDocuments(newPage, documentPagination.pageSize);
        };
        
        // 处理文档页面大小切换
        const handleDocumentPageSizeChange = (newPageSize) => {
            documentPagination.pageSize = newPageSize;
            loadDocuments(1, newPageSize); // 切换页面大小时回到第一页
        };
        
        // 加载智能体列表
        const loadAgents = async () => {
            try {
                console.log('🤖 开始加载智能体列表...');
                const response = await http.get('/api/agents');
                console.log('🤖 API响应完整对象:', response);
                console.log('🤖 API响应状态:', response.status);
                console.log('🤖 API响应数据:', response.data);
                console.log('🤖 响应数据类型:', typeof response.data);
                console.log('🤖 响应数据是否为数组:', Array.isArray(response.data));
                
                // 检查响应数据结构
                let agentData = [];
                if (response.data && typeof response.data === 'object' && 'agents' in response.data) {
                    console.log('🤖 使用 response.data.agents 格式');
                    agentData = response.data.agents || [];
                } else if (Array.isArray(response.data)) {
                    console.log('🤖 使用直接数组格式');
                    agentData = response.data;
                } else {
                    console.warn('🤖 智能体数据格式不正确:', response.data);
                    agentData = [];
                }
                
                console.log('🤖 解析后的agentData:', agentData);
                console.log('🤖 agentData数组长度:', agentData.length);
                
                // 直接设置数据
                agents.value = agentData;
                
                console.log('🤖 设置agents.value为:', agents.value);
                console.log('🤖 agents.value.length:', agents.value.length);
                console.log('🤖 agents.value是否为响应式:', agents.value);
                
                // 强制重新渲染
                agentListKey.value++;
                console.log('🤖 agentListKey更新为:', agentListKey.value);
                
                // 等待DOM更新
                await nextTick();
                console.log('🤖 nextTick后 - 检查DOM...');
                
                // 检查DOM中的元素
                setTimeout(() => {
                    const agentElements = document.querySelectorAll('.agent-card');
                    console.log('🤖 DOM中找到的agent卡片数量:', agentElements.length);
                    console.log('🤖 agent卡片元素:', agentElements);
                    
                    if (agentElements.length === 0) {
                        console.error('🤖 DOM中没有找到agent卡片元素！');
                        // 检查是否是标签页问题
                        const agentTab = document.querySelector('el-tab-pane[name="agents"]');
                        console.log('🤖 智能体标签页元素:', agentTab);
                        console.log('🤖 当前活动标签页:', activeMainTab.value);
                    }
                }, 100);
                
                return true;
            } catch (error) {
                console.error('🤖 获取智能体列表失败', error);
                console.error('🤖 错误详情:', error.response);
                if (error.response && error.response.status === 401) {
                    console.log('🤖 未授权访问，需要登录');
                    handleLogout();
                } else {
                    ElMessage.error('获取智能体列表失败');
                }
                agents.value = [];
                return false;
            }
        };
        
        // 选择对话
        const selectConversation = async (conversation) => {
            console.log('💬 选择对话:', conversation);
            selectedConversation.value = conversation;
            conversationMessages.value = []; // 清空之前的消息
            currentMessage.value = '';
            
            // 加载对话消息
            await loadConversationMessages(conversation.id);
            ElMessage.success(`已打开对话: ${conversation.title}`);
        };
        
        // 创建新对话
        const createNewConversation = () => {
            newConversationTitle.value = '新对话';
            setTimeout(() => {
                newConversationDialogVisible.value = true;
            }, 100);
        };
        
        // 确认创建新对话
        const confirmCreateConversation = () => {
            if (!newConversationTitle.value.trim()) {
                ElMessage.warning('请输入对话标题');
                return;
            }
            
            console.log('💬 创建新对话:', newConversationTitle.value);
            ElMessage.success('对话创建成功');
            newConversationDialogVisible.value = false;
            newConversationTitle.value = '';
        };
        
        // 发送消息
        const sendMessage = async () => {
            // 检查是否在对话详情页面，使用不同的输入框
            const messageInput = selectedConversation.value ? currentMessage.value : newMessage.value;
            if (!messageInput.trim() || !selectedConversation.value) {
                return;
            }
            
            if (sendingMessage.value) {
                return;
            }
            
            const userMessage = messageInput.trim();
            sendingMessage.value = true;
            
            // 清空对应的输入框
            if (selectedConversation.value) {
                currentMessage.value = '';
                
                // 添加用户消息到对话详情页面
                const userMsg = {
                    id: Date.now(),
                    content: userMessage,
                    message_type: 'user',
                    created_at: new Date().toISOString()
                };
                conversationMessages.value.push(userMsg);
                
                // 滚动到底部（发送消息时使用平滑模式）
                await nextTick();
                scrollToMessagesBottom(false);
                
                try {
                    if (useStreamingMode.value) {
                        // 流式发送消息到对话详情页面
                        await sendStreamingMessageToConversation(userMessage);
                    } else {
                        // 非流式发送消息到对话详情页面
                        await sendNormalMessageToConversation(userMessage);
                    }
                } catch (error) {
                    console.error('发送消息失败:', error);
                    ElMessage.error('发送消息失败');
                }
            } else {
                // 原来的主对话逻辑
                newMessage.value = '';
                
                // 添加用户消息到UI
                const userMsg = {
                    id: Date.now(),
                    content: userMessage,
                    role: 'user',
                    created_at: new Date().toISOString()
                };
                messages.value.push(userMsg);
                
                await nextTick();
                if (!userScrolling.value) {
                    scrollToBottom();
                }
                
                try {
                    if (useStreamingMode.value) {
                        await sendStreamingMessage(userMessage);
                    } else {
                        await sendNormalMessage(userMessage);
                    }
                } catch (error) {
                    console.error('发送消息失败', error);
                    ElMessage.error('发送消息失败');
                }
            }
            
            sendingMessage.value = false;
            currentStreamingMessage.value = null;
        };
        
        // 流式发送消息 - 修复为正确的API调用方式
        const sendStreamingMessage = (userMessage) => {
            console.log("发送流式消息到对话，ID:", selectedConversation.value.id, "内容:", userMessage);
            
            // 创建一个空的助手消息占位符
            let assistantMessage = {
                id: Date.now() + 1,
                content: '',
                message_type: 'assistant',
                created_at: new Date().toISOString(),
                referenced_documents: []
            };
            
            // 添加到消息列表
            messages.value.push(assistantMessage);
            currentStreamingMessage.value = assistantMessage;
            
            // 只在用户未手动滚动时滚动到底部
            if (!userScrolling.value) {
                scrollToBottom();
            }
            
            // 创建SSE连接 - 使用正确的API路径
            const url = `/api/qa/conversations/${selectedConversation.value.id}/messages/stream`;
            const params = new URLSearchParams({
                content: userMessage,
                token: token.value,
                model: selectedModel.value
            });
            console.log("创建流式连接，参数:", params.toString());
            const eventSource = new EventSource(`${url}?${params}`);
            
            let isConnected = false;
            let currentContent = '';
            
            eventSource.onopen = () => {
                console.log("流式连接已建立");
                isConnected = true;
            };
            
            eventSource.onmessage = (event) => {
                console.log("收到流式数据:", event.data);
                
                if (event.data === '[DONE]') {
                    console.log("流式响应完成");
                    eventSource.close();
                    currentStreamingMessage.value = null;
                    return;
                }
                
                try {
                    const data = JSON.parse(event.data);
                    console.log("解析后的数据:", data);
                    
                    // 处理增量内容
                    if (data.answer_delta) {
                        currentContent += data.answer_delta;
                        assistantMessage.content = currentContent;
                        
                        // 触发响应式更新
                        messages.value = [...messages.value];
                        
                        // 自动滚动到底部
                        if (!userScrolling.value) {
                            nextTick(() => scrollToBottom());
                        }
                    }
                    
                    // 处理引用文档
                    if (data.referenced_documents && data.referenced_documents.length > 0) {
                        console.log("收到引用文档:", data.referenced_documents);
                        assistantMessage.referenced_documents = data.referenced_documents;
                        // 触发响应式更新
                        messages.value = [...messages.value];
                    }
                    
                    // 检查是否完成
                    if (data.finished === true) {
                        console.log("流式响应完成，主动关闭连接");
                        eventSource.close();
                        currentStreamingMessage.value = null;
                        return;
                    }
                    
                } catch (e) {
                    console.error("解析流式数据失败:", e, "原始数据:", event.data);
                }
            };
            
            eventSource.onerror = (error) => {
                console.error("流式连接错误:", error);
                console.error("连接状态:", eventSource.readyState);
                
                // 如果是正常结束（EventSource.CLOSED = 2），不显示错误
                if (eventSource.readyState === EventSource.CLOSED) {
                    console.log("流式连接正常结束");
                    currentStreamingMessage.value = null;
                    return;
                }
                
                if (!isConnected) {
                    ElMessage.error('无法建立流式连接，请检查网络');
                    assistantMessage.content = '连接失败，请重试';
                } else {
                    console.log("流式连接意外中断，但可能已经接收到部分数据");
                }
                
                eventSource.close();
                currentStreamingMessage.value = null;
            };
            
            // 设置超时处理
            setTimeout(() => {
                if (eventSource.readyState !== EventSource.CLOSED) {
                    console.warn("流式响应超时，关闭连接");
                    eventSource.close();
                    currentStreamingMessage.value = null;
                    if (!assistantMessage.content) {
                        assistantMessage.content = '响应超时，请重试';
                        messages.value = [...messages.value];
                    }
                }
            }, 120000); // 2分钟超时
        };
        
        // 普通发送消息
        const sendNormalMessage = async (userMessage) => {
            console.log("发送普通消息到对话，ID:", selectedConversation.value.id, "内容:", userMessage);
            
            try {
                // 调用正确的API端点
                const response = await http.post(`/api/qa/conversations/${selectedConversation.value.id}/messages`, {
                    content: userMessage,
                    model: selectedModel.value
                });
                console.log("发送消息响应:", response.data);
                
                // 处理响应数据
                let processedResponse = {...response.data};
                
                // 如果有文档引用，统一格式
                if (processedResponse.referenced_documents && processedResponse.referenced_documents.length > 0) {
                    console.log("处理非流式响应的文档引用，原始:", processedResponse.referenced_documents);
                    
                    // 转换格式，保持与流式响应一致
                    processedResponse.referenced_documents = processedResponse.referenced_documents.map(doc => {
                        return {
                            document_id: doc.id,
                            title: doc.title,
                            relevance_score: doc.relevance_score,
                            content_preview: doc.content_preview || `文档ID: ${doc.id}, 标题: ${doc.title}`
                        };
                    });
                    
                    console.log("处理非流式响应的文档引用，转换后:", processedResponse.referenced_documents);
                }
                
                // 添加助手回复
                messages.value.push(processedResponse);
                
                // 只有在用户未手动滚动时才滚动到底部
                if (!userScrolling.value) {
                    await nextTick();
                    scrollToBottom();
                }
                
            } catch (error) {
                console.error('发送普通消息失败', error);
                throw error;
            }
        };
        
        // 对话详情页面的非流式发送消息
        const sendNormalMessageToConversation = async (userMessage) => {
            try {
                console.log("发送非流式消息到对话，ID:", selectedConversation.value.id, "内容:", userMessage);
                
                const response = await http.post(`/api/qa/conversations/${selectedConversation.value.id}/messages`, {
                    content: userMessage,
                    model: selectedModel.value
                });
                console.log("发送消息响应:", response.data);
                
                // 处理响应数据
                let processedResponse = {...response.data};
                
                // 如果有文档引用，统一格式
                if (processedResponse.referenced_documents && processedResponse.referenced_documents.length > 0) {
                    console.log("处理非流式响应的文档引用，原始:", processedResponse.referenced_documents);
                    
                    // 转换格式，保持与流式响应一致
                    processedResponse.referenced_documents = processedResponse.referenced_documents.map(doc => {
                        return {
                            document_id: doc.id,
                            title: doc.title,
                            relevance_score: doc.relevance_score,
                            content_preview: doc.content_preview || `文档ID: ${doc.id}, 标题: ${doc.title}`
                        };
                    });
                    
                    console.log("处理非流式响应的文档引用，转换后:", processedResponse.referenced_documents);
                }
                
                // 添加助手回复到对话详情页面
                conversationMessages.value.push(processedResponse);
                await nextTick();
                scrollToMessagesBottom(false);
                
            } catch (error) {
                console.error('发送非流式消息失败', error);
                throw error;
            }
        };
        
        // 对话详情页面的流式发送消息
        const sendStreamingMessageToConversation = async (userMessage) => {
            console.log("发送流式消息到对话，ID:", selectedConversation.value.id, "内容:", userMessage);
            
            // 创建一个空的助手消息占位符
            let assistantMessage = {
                id: Date.now() + 1,
                content: '',
                message_type: 'assistant',
                created_at: new Date().toISOString(),
                referenced_documents: []
            };
            
            // 添加到消息列表
            conversationMessages.value.push(assistantMessage);
            currentStreamingMessage.value = assistantMessage;
            
            // 滚动到底部
            await nextTick();
            scrollToMessagesBottom(false);
            
            // 创建SSE连接，添加认证token
            const token = localStorage.getItem('token');
            const eventSource = new EventSource(`/api/qa/conversations/${selectedConversation.value.id}/messages/stream?content=${encodeURIComponent(userMessage)}&model=${encodeURIComponent(selectedModel.value)}&token=${encodeURIComponent(token)}`);
            
            eventSource.onmessage = function(event) {
                try {
                    const data = JSON.parse(event.data);
                    console.log('收到流式数据:', data);
                    
                    // 处理后端返回的数据格式
                    if (data.answer_delta && data.answer_delta.trim()) {
                        // 更新消息内容
                        assistantMessage.content += data.answer_delta;
                        // 触发响应式更新
                        conversationMessages.value = [...conversationMessages.value];
                        
                        // 滚动到底部
                        nextTick(() => {
                            scrollToMessagesBottom(false);
                        });
                    }
                    
                    // 处理引用文档
                    if (data.referenced_documents && data.referenced_documents.length > 0) {
                        console.log("收到引用文档:", data.referenced_documents);
                        assistantMessage.referenced_documents = data.referenced_documents;
                        // 触发响应式更新
                        conversationMessages.value = [...conversationMessages.value];
                    }
                    
                    // 检查是否完成
                    if (data.finished === true) {
                        console.log('流式响应完成');
                        eventSource.close();
                        currentStreamingMessage.value = null;
                    }
                } catch (error) {
                    console.error('解析流式数据失败:', error, 'Raw data:', event.data);
                }
            };
            
            eventSource.onerror = function(event) {
                console.error('SSE连接错误:', event);
                eventSource.close();
                currentStreamingMessage.value = null;
                ElMessage.error('消息发送失败，请重试');
            };
            
            // 10秒超时处理
            setTimeout(() => {
                if (eventSource.readyState !== EventSource.CLOSED) {
                    console.log('SSE连接超时，关闭连接');
                    eventSource.close();
                    currentStreamingMessage.value = null;
                }
            }, 10000);
        };
        
        // 文件上传处理
        const handleFileUpload = (file) => {
            uploadForm.file = file.raw;
            if (!uploadForm.title) {
                uploadForm.title = file.name.split('.')[0];
            }
            return false;
        };
        
        // 上传文档
        const uploadDocument = async () => {
            if (!uploadForm.file || !uploadForm.title.trim()) {
                ElMessage.warning('请选择文件并输入标题');
                return;
            }
            
            uploading.value = true;
            const formData = new FormData();
            formData.append('file', uploadForm.file);
            formData.append('title', uploadForm.title.trim());
            formData.append('description', uploadForm.description.trim());
            
            try {
                await http.post('/api/documents/upload', formData, {
                    headers: { 'Content-Type': 'multipart/form-data' }
                });
                
                uploadDialogVisible.value = false;
                uploadForm.title = '';
                uploadForm.description = '';
                uploadForm.file = null;
                
                await loadDocuments();
                ElMessage.success('文档上传成功');
            } catch (error) {
                console.error('文档上传失败', error);
                ElMessage.error('文档上传失败');
            } finally {
                uploading.value = false;
            }
        };
        
        // 删除文档
        const deleteDocument = async (doc) => {
            try {
                await ElMessageBox.confirm('确定要删除这个文档吗？', '确认删除', {
                    type: 'warning'
                });
                
                await http.delete(`/api/documents/${doc.id}`);
                await loadDocuments();
                ElMessage.success('文档删除成功');
            } catch (error) {
                if (error !== 'cancel') {
                    console.error('删除文档失败', error);
                    ElMessage.error('删除文档失败');
                }
            }
        };
        
        // 搜索文档
        const searchDocuments = async () => {
            if (!searchQuery.value.trim()) {
                return;
            }
            
            searching.value = true;
            try {
                const response = await http.post('/api/qa/retrieval/search', {
                    query: searchQuery.value.trim(),
                    top_k: 10
                });
                searchResults.value = response.data.results || [];
            } catch (error) {
                console.error('搜索失败', error);
                ElMessage.error('搜索失败');
            } finally {
                searching.value = false;
            }
        };
        
        // 下载文档
        const downloadDocument = async (document) => {
            try {
                const response = await http.get(`/api/documents/${document.id}/download`, {
                    responseType: 'blob'
                });
                
                // 创建下载链接
                const url = window.URL.createObjectURL(new Blob([response.data]));
                const link = document.createElement('a');
                link.href = url;
                link.setAttribute('download', document.title || `document_${document.id}`);
                document.body.appendChild(link);
                link.click();
                link.remove();
                window.URL.revokeObjectURL(url);
                
                ElMessage.success('文档下载成功');
            } catch (error) {
                console.error('下载文档失败', error);
                ElMessage.error('下载文档失败');
            }
        };
        
        // 查看文档详情
        const viewDocumentDetail = async (doc) => {
            try {
                console.log('📖 查看文档详情:', doc);
                loadingDocumentDetail.value = true;
                documentDetailVisible.value = true;
                
                // 获取文档详细信息
                const response = await http.get(`/api/documents/${doc.document_id}`);
                selectedDocumentDetail.value = {
                    ...response.data,
                    content_preview: doc.content_preview || response.data.content_preview,
                    relevance_score: doc.relevance_score
                };
                
                console.log('📖 文档详情加载成功:', selectedDocumentDetail.value);
            } catch (error) {
                console.error('获取文档详情失败:', error);
                ElMessage.error('获取文档详情失败');
                documentDetailVisible.value = false;
            } finally {
                loadingDocumentDetail.value = false;
            }
        };
        
        // 关闭文档详情对话框
        const closeDocumentDetail = () => {
            documentDetailVisible.value = false;
            selectedDocumentDetail.value = null;
        };
        
        // 智能体相关方法
        const selectAgent = async (agent) => {
            console.log('🤖 选择智能体:', agent);
            selectedAgent.value = agent;
            agentExecutions.value = []; // 清空之前的执行历史
            
            // 加载智能体的历史执行记录
            try {
                console.log('🤖 加载智能体执行历史...');
                const response = await http.get(`/api/agents/${agent.id}/executions`);
                if (response.data && Array.isArray(response.data)) {
                    // 转换后端数据格式以匹配前端期望的格式
                    agentExecutions.value = response.data.map(execution => ({
                        id: execution.id,
                        user_input: execution.user_input,
                        agent_output: execution.agent_output, // 使用正确的字段名
                        response: execution.agent_output,     // 保持兼容性
                        status: execution.status || 'completed',
                        execution_time: execution.execution_time,
                        tools_used: execution.tools_used || [],
                        created_at: execution.completed_at || execution.started_at,
                        started_at: execution.started_at,
                        isExecuting: false
                    }));
                    console.log('🤖 智能体执行历史加载成功:', agentExecutions.value);
                    
                    if (agentExecutions.value.length > 0) {
                        ElMessage.success(`已选择智能体: ${agent.name}，加载了 ${agentExecutions.value.length} 条历史记录`);
                    } else {
                        ElMessage.success(`已选择智能体: ${agent.name}`);
                    }
                } else {
                    console.log('🤖 执行历史为空或格式不正确');
                    ElMessage.success(`已选择智能体: ${agent.name}`);
                }
            } catch (error) {
                console.error('🤖 加载智能体执行历史失败:', error);
                if (error.response && error.response.status !== 404) {
                    ElMessage.warning('加载执行历史失败，但不影响使用');
                }
                ElMessage.success(`已选择智能体: ${agent.name}`);
            }
        };
        
        // 加载对话消息
        const loadConversationMessages = async (conversationId) => {
            try {
                const response = await http.get(`/api/qa/conversations/${conversationId}`);
                conversationMessages.value = response.data.messages || [];
                console.log('📝 加载对话消息:', conversationMessages.value);
                
                // 加载完成后立即跳转到底部，无滚动动画
                await nextTick();
                setTimeout(() => {
                    console.log('开始立即跳转到底部...');
                    scrollToMessagesBottom(true); // 使用立即模式
                }, 300);
            } catch (error) {
                console.error('加载对话消息失败:', error);
                ElMessage.error('加载对话消息失败');
            }
        };
        
        // 滚动到消息底部
        const scrollToMessagesBottom = (instant = false) => {
            console.log('🎯 开始执行滚动到底部, 立即模式:', instant);
            
            const performScroll = (attempt = 1) => {
                console.log(`📍 尝试滚动第${attempt}次`);
                
                // 尝试多种选择器
                const selectors = [
                    '[ref="messagesContainer"]',
                    '.el-tab-pane.is-active [ref="messagesContainer"]',
                    'div[style*="overflow-y: auto"]'
                ];
                
                let container = null;
                for (const selector of selectors) {
                    container = document.querySelector(selector);
                    if (container) {
                        console.log(`✅ 找到容器 (选择器: ${selector}):`, container);
                        break;
                    } else {
                        console.log(`❌ 选择器未找到容器: ${selector}`);
                    }
                }
                
                if (container) {
                    console.log(`📊 容器信息:`, {
                        scrollHeight: container.scrollHeight,
                        clientHeight: container.clientHeight,
                        scrollTop: container.scrollTop,
                        offsetHeight: container.offsetHeight
                    });
                    
                    if (container.scrollHeight > container.clientHeight) {
                        if (instant) {
                            // 立即跳转到底部，无动画
                            console.log('🚀 执行立即跳转');
                            container.style.scrollBehavior = 'auto';
                            const targetScroll = container.scrollHeight - container.clientHeight;
                            container.scrollTop = targetScroll;
                            
                            // 立即验证
                            setTimeout(() => {
                                console.log(`✅ 立即跳转完成, 目标: ${targetScroll}, 实际: ${container.scrollTop}`);
                            }, 10);
                        } else {
                            // 平滑滚动到底部
                            console.log('🌊 执行平滑滚动');
                            container.style.scrollBehavior = 'smooth';
                            container.scrollTop = container.scrollHeight;
                            console.log('平滑滚动已触发');
                        }
                    } else {
                        console.log('⚠️ 内容高度不足，无需滚动');
                    }
                } else {
                    console.log(`❌ 未找到消息容器 (第${attempt}次尝试)`);
                    if (attempt < 5) {
                        console.log(`⏰ 等待200ms后重试...`);
                        setTimeout(() => performScroll(attempt + 1), 200);
                    } else {
                        console.error('🔥 多次尝试后仍未找到容器');
                    }
                }
            };
            
            // 立即模式减少延迟
            if (instant) {
                console.log('⚡ 立即模式：使用nextTick直接执行');
                nextTick(() => performScroll());
            } else {
                console.log('⏱️ 平滑模式：延迟100ms执行');
                nextTick(() => {
                    setTimeout(() => performScroll(), 100);
                });
            }
        };
        
        // 格式化Markdown
        const formatMarkdown = (content) => {
            if (typeof marked !== 'undefined') {
                return marked.parse(content);
            }
            return content.replace(/\n/g, '<br>');
        };
        
        // 格式化工具名称，将英文工具名转换为中文说明
        const formatToolNames = (tools) => {
            if (!tools || !Array.isArray(tools)) {
                return '';
            }
            
            const toolNameMap = {
                'web_search': '网络搜索',
                'document_search': '文档搜索',
                'calculator': '计算器',
                'python_repl': 'Python执行器',
                'file_reader': '文件读取',
                'email_sender': '邮件发送',
                'calendar': '日历管理',
                'weather': '天气查询'
            };
            
            return tools.map(tool => toolNameMap[tool] || tool).join(', ');
        };
        
        const executeAgent = async () => {
            if (!agentInput.value.trim() || !selectedAgent.value || !selectedAgent.value.id) {
                ElMessage.warning('请选择智能体并输入任务内容');
                return;
            }
            
            if (executingAgent.value) {
                return;
            }
            
            const input = agentInput.value.trim();
            executingAgent.value = true;
            
            // 创建一个临时执行记录，显示正在执行状态
            const tempExecution = {
                id: Date.now(),
                user_input: input,
                agent_output: '正在执行中...',
                response: '正在执行中...',
                status: 'executing',
                execution_time: null,
                tools_used: [],
                created_at: new Date().toISOString(),
                isExecuting: true
            };
            
            // 添加临时记录到列表顶部
            agentExecutions.value.unshift(tempExecution);
            agentInput.value = '';
            
            // 滚动到底部显示执行状态
            await nextTick();
            setTimeout(() => {
                const agentChatContainer = document.querySelector('[style*="flex: 1; overflow-y: auto; padding: 20px"]');
                if (agentChatContainer) {
                    agentChatContainer.scrollTop = agentChatContainer.scrollHeight;
                }
            }, 100);
            
            try {
                const response = await http.post('/api/agents/execute', {
                    agent_id: selectedAgent.value.id,
                    user_input: input
                });
                
                console.log('智能体执行响应数据:', response.data);
                
                // 更新临时记录为实际结果
                const executionResult = {
                    id: response.data.id || tempExecution.id,
                    user_input: input,
                    agent_output: response.data.agent_output || '执行完成，但没有返回结果',
                    response: response.data.agent_output || '执行完成，但没有返回结果',
                    status: 'completed',
                    execution_time: response.data.execution_time,
                    tools_used: response.data.tools_used || [],
                    created_at: new Date().toISOString(),
                    isExecuting: false
                };
                
                // 替换临时记录
                agentExecutions.value[0] = executionResult;
                
                console.log('执行结果已更新:', executionResult);
                
                // 再次滚动到底部显示结果
                await nextTick();
                setTimeout(() => {
                    const agentChatContainer = document.querySelector('[style*="flex: 1; overflow-y: auto; padding: 20px"]');
                    if (agentChatContainer) {
                        agentChatContainer.scrollTop = agentChatContainer.scrollHeight;
                    }
                }, 100);
                
                ElMessage.success('智能体执行完成');
            } catch (error) {
                console.error('智能体执行失败', error);
                
                // 更新临时记录为错误状态
                const errorMessage = '执行失败: ' + (error.response?.data?.detail || error.message || '未知错误');
                agentExecutions.value[0] = {
                    ...tempExecution,
                    agent_output: errorMessage,
                    response: errorMessage,
                    status: 'failed',
                    isExecuting: false
                };
                
                ElMessage.error('智能体执行失败');
            } finally {
                executingAgent.value = false;
            }
        };
        
        // Tab切换处理
        const handleTabClick = (tab) => {
            console.log('切换到标签页:', tab.props.name);
            if (tab.props.name === 'agents') {
                console.log('切换到智能体标签页，重新加载agents...');
                loadAgents();
            } else if (tab.props.name === 'qa') {
                console.log('切换到问答标签页，重新加载conversations...');
                loadConversations();
            } else if (tab.props.name === 'documents') {
                console.log('切换到文档标签页，重新加载documents...');
                loadDocuments();
            }
        };
        
        const createAgent = async () => {
            if (!createAgentForm.name.trim()) {
                ElMessage.warning('请输入智能体名称');
                return;
            }
            
            creatingAgent.value = true;
            try {
                await http.post('/api/agents', createAgentForm);
                
                showCreateAgentDialog.value = false;
                createAgentForm.name = '';
                createAgentForm.description = '';
                createAgentForm.system_prompt = '你是一个智能助手，可以使用各种工具来帮助用户完成任务。';
                
                await loadAgents();
                ElMessage.success('智能体创建成功');
            } catch (error) {
                console.error('创建智能体失败', error);
                ElMessage.error('创建智能体失败');
            } finally {
                creatingAgent.value = false;
            }
        };
        
        // 滚动相关
        const scrollToBottom = () => {
            // 检查是否在正确的标签页
            if (activeMainTab.value !== 'qa') {
                return;
            }
            
            if (!selectedConversation.value) {
                return;
            }
            
            // 尝试多种选择器
            const selectors = [
                '.messages-container',
                '[ref="messagesContainer"]',
                '.el-tab-pane[id="tab-qa"] .messages-container',
                '.el-tab-pane.is-active .messages-container'
            ];
            
            let container = null;
            for (const selector of selectors) {
                container = document.querySelector(selector);
                if (container) break;
            }
            
            if (container) {
                // 强制滚动到底部
                const targetScroll = container.scrollHeight - container.clientHeight;
                container.scrollTop = targetScroll;
                showScrollToBottom.value = false;
            }
        };

        // 处理滚动事件，检测是否需要显示"回到底部"按钮
        const handleScroll = () => {
            const container = document.querySelector('.messages-container');
            if (container) {
                const { scrollTop, scrollHeight, clientHeight } = container;
                // 如果距离底部超过100px，显示"回到底部"按钮
                showScrollToBottom.value = scrollHeight - (scrollTop + clientHeight) > 100;
            }
        };
        
        const setupScrollListener = () => {
            setTimeout(() => {
                const container = document.querySelector('.messages-container');
                if (container) {
                    container.addEventListener('scroll', () => {
                        const { scrollTop, scrollHeight, clientHeight } = container;
                        userScrolling.value = scrollTop < scrollHeight - clientHeight - 50;
                        handleScroll(); // 同时检测是否需要显示"回到底部"按钮
                    });
                }
            }, 1000);
        };
        
        // 监听消息变化，自动滚动
        watch(messages, (newMessages, oldMessages) => {
            console.log('消息变化检测:', {
                新消息数量: newMessages.length,
                旧消息数量: oldMessages?.length || 0,
                用户正在滚动: userScrolling.value
            });
            if (!userScrolling.value) {
                console.log('触发自动滚动到底部');
                nextTick(() => scrollToBottom());
            } else {
                console.log('用户正在手动滚动，跳过自动滚动');
            }
        }, { deep: true });
        
        // 监听标签页切换，确保数据及时更新
        watch(activeMainTab, async (newTab, oldTab) => {
            console.log(`标签页切换: ${oldTab} -> ${newTab}`);
            
            if (newTab === 'agents') {
                console.log('切换到智能体标签页，重新加载数据...');
                // 重置选中的智能体，显示列表
                selectedAgent.value = null;
                // 重新加载智能体数据
                await loadAgents();
            } else if (newTab === 'qa') {
                console.log('切换到问答标签页，重新加载数据...');
                // 重置选中的对话，显示列表
                selectedConversation.value = null;
                await loadConversations();
            } else if (newTab === 'documents') {
                console.log('切换到文档标签页，重新加载数据...');
                await loadDocuments();
            }
        });
        
        // 监听对话消息变化，自动滚动到底部
        watch(conversationMessages, (newMessages, oldMessages) => {
            console.log('🔄 对话消息变化触发:', {
                新消息数量: newMessages.length,
                旧消息数量: oldMessages?.length || 0,
                是否有新消息: newMessages.length > 0
            });
            
            if (newMessages.length > 0) {
                // 判断是初次加载还是新增消息
                const isInitialLoad = !oldMessages || oldMessages.length === 0;
                const isNewMessage = oldMessages && newMessages.length > oldMessages.length;
                
                console.log('📋 场景判断:', {
                    isInitialLoad,
                    isNewMessage,
                    oldMessages: oldMessages?.length || 0,
                    newMessages: newMessages.length
                });
                
                if (isInitialLoad) {
                    // 初次加载对话：立即跳转到底部
                    console.log('🎯 初次加载对话，立即跳转到底部');
                    nextTick(() => {
                        setTimeout(() => {
                            scrollToMessagesBottom(true); // 使用立即模式
                        }, 100); // 稍微延迟确保DOM更新
                    });
                } else if (isNewMessage) {
                    // 新增消息：平滑滚动到底部
                    console.log('💬 新增消息，平滑滚动到底部');
                    nextTick(() => {
                        scrollToMessagesBottom(false); // 使用平滑模式
                    });
                } else {
                    console.log('ℹ️ 消息数组变化但非新增或初始加载，跳过滚动');
                }
            } else {
                console.log('⚠️ 消息数组为空，跳过滚动');
            }
        }, { deep: true, immediate: false });
        
        // 监听智能体执行历史变化，自动滚动到底部
        watch(agentExecutions, (newExecutions, oldExecutions) => {
            if (newExecutions.length > 0 && newExecutions.length !== oldExecutions?.length) {
                console.log('智能体执行历史变化，自动滚动到底部');
                setTimeout(() => {
                    const container = document.querySelector('.agent-detail-card .overflow-y-auto');
                    if (container) {
                        container.scrollTop = container.scrollHeight;
                    }
                }, 100);
            }
        }, { deep: true });
        
        return {
            // 状态
            isLoggedIn,
            loading,
            activeTab,
            activeMainTab,
            userInfo,
            
            // 表单
            loginForm,
            registerForm,
            
            // 对话
            conversations,
            selectedConversation,
            conversationMessages,
            currentMessage,
            messages,
            newMessage,
            sendingMessage,
            useStreamingMode,
            selectedModel,
            modelOptions,
            newConversationDialogVisible,
            newConversationTitle,
            showScrollToBottom,
            
            // 文档
            documents,
            documentPagination,
            uploadDialogVisible,
            uploading,
            uploadForm,
            searchQuery,
            searchResults,
            searching,
            documentDetailVisible,
            selectedDocumentDetail,
            loadingDocumentDetail,
            
            // 智能体
            agents,
            selectedAgent,
            agentExecutions,
            agentInput,
            agentListKey,
            executingAgent,
            showCreateAgentDialog,
            creatingAgent,
            createAgentForm,
            
            // 方法
            handleLogin,
            handleRegister,
            handleLogout,
            loadConversations,
            loadDocuments,
            loadAgents,
            selectConversation,
            createNewConversation,
            confirmCreateConversation,
            sendMessage,
            sendNormalMessageToConversation,
            sendStreamingMessageToConversation,
            handleFileUpload,
            uploadDocument,
            deleteDocument,
            downloadDocument,
            viewDocumentDetail,
            closeDocumentDetail,
            searchDocuments,
            handleDocumentPageChange,
            handleDocumentPageSizeChange,
            selectAgent,
            executeAgent,
            createAgent,
            handleTabClick,
            formatDate,
            scrollToBottom,
            handleScroll,
            loadConversationMessages,
            scrollToMessagesBottom,
            formatMarkdown,
            formatToolNames,
            
            // 工具方法
            getAgentTypeLabel: (type) => {
                const labels = {
                    'react': 'ReAct',
                    'openai_functions': 'OpenAI Functions',
                    'structured_chat': 'Structured Chat',
                    'conversational': 'Conversational'
                };
                return labels[type] || type;
            },
            
            // 获取工具列表显示文本
            getToolsDisplay: (tools) => {
                if (!tools) return '无';
                
                // 如果是字符串，尝试解析为JSON
                if (typeof tools === 'string') {
                    try {
                        const parsed = JSON.parse(tools);
                        return Array.isArray(parsed) ? parsed.join(', ') : tools;
                    } catch (e) {
                        return tools;
                    }
                }
                
                // 如果是数组，直接join
                if (Array.isArray(tools)) {
                    return tools.join(', ');
                }
                
                return String(tools);
            },
            
            // 格式化文件大小
            formatFileSize: (bytes) => {
                if (!bytes) return '0 B';
                const sizes = ['B', 'KB', 'MB', 'GB'];
                const i = Math.floor(Math.log(bytes) / Math.log(1024));
                return Math.round(bytes / Math.pow(1024, i) * 100) / 100 + ' ' + sizes[i];
            }
        };
    }
});

// 添加全局调试函数
window.debugApp = {
    checkData: () => {
        const instance = app._instance;
        if (instance) {
            console.log('=== 调试信息 ===');
            console.log('agents:', instance.setupState.agents.value);
            console.log('conversations:', instance.setupState.conversations.value);
            console.log('documents:', instance.setupState.documents.value);
            console.log('isLoggedIn:', instance.setupState.isLoggedIn.value);
            console.log('token:', instance.setupState.token.value);
            console.log('===============');
        }
    },
    reloadAgents: () => {
        const instance = app._instance;
        if (instance) {
            instance.setupState.loadAgents();
        }
    },
    reloadConversations: () => {
        const instance = app._instance;
        if (instance) {
            instance.setupState.loadConversations();
        }
    },
    reloadDocuments: () => {
        const instance = app._instance;
        if (instance) {
            instance.setupState.loadDocuments();
        }
    },
    forceUpdate: () => {
        const instance = app._instance;
        if (instance) {
            console.log('🔄 强制更新所有数据...');
            // 强制设置为空然后重新加载
            instance.setupState.agents.value = [];
            instance.setupState.conversations.value = [];
            instance.setupState.documents.value = [];
            
            // 等待一个tick然后重新加载
            setTimeout(() => {
                instance.setupState.loadAgents();
                instance.setupState.loadConversations();
                instance.setupState.loadDocuments();
            }, 100);
        }
    }
};

// 使用Element Plus
app.use(ElementPlus);

// 挂载应用
app.mount('#app');

console.log('🎯 应用已挂载，可使用 window.debugApp.checkData() 查看数据状态');