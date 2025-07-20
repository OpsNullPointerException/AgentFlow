// 创建Vue应用
const { createApp, ref, reactive, onMounted, nextTick, watch } = Vue;

// 确保Element Plus全局可用
const ElementPlus = window.ElementPlus;
const { ElMessage } = ElementPlus;

// 设置API基础路径
const API_BASE_URL = '';  // 将API基础路径设置为空，避免路径重复

const app = createApp({
    setup() {
        // 身份验证状态
        const isLoggedIn = ref(false);
        const token = ref(localStorage.getItem('token') || '');
        const userInfo = ref({});
        const loading = ref(false);
        const activeTab = ref('login');
        
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
        const messages = ref([]);
        const newMessage = ref('');
        const sendingMessage = ref(false);
        const useStreamingMode = ref(true);  // 默认使用流式响应
        const currentStreamingMessage = ref(null);  // 当前正在流式生成的消息
        const selectedModel = ref('qwen-turbo');  // 默认使用更快的模型
        const newConversationDialogVisible = ref(false);
        const newConversationTitle = ref('');
        
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
        
        // 搜索相关
        const searchQuery = ref('');
        const searchResults = ref([]);
        const searching = ref(false);
        
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
            if (token.value) {
                try {
                    // 获取用户信息
                    const response = await http.get('/api/accounts/me');
                    userInfo.value = response.data;
                    isLoggedIn.value = true;
                    
                    // 加载对话和文档
                    loadConversations();
                    loadDocuments();
                } catch (error) {
                    console.error('获取用户信息失败', error);
                    handleLogout();
                }
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
                ElementPlus.ElMessage.warning('请输入用户名和密码');
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
                console.log("用户信息加载成功:", userInfo.value);
                isLoggedIn.value = true;
                
                // 加载对话和文档
                await loadConversations();
                await loadDocuments();
                
                // 添加额外调试信息
                console.log("对话列表:", conversations.value);
                console.log("文档列表:", documents.value);
                
                ElementPlus.ElMessage.success('登录成功');
            } catch (error) {
                console.error('登录失败', error);
                ElementPlus.ElMessage.error(error.response?.data?.detail || '登录失败，请检查用户名和密码');
            } finally {
                loading.value = false;
            }
        };
        
        // 注册处理
        const handleRegister = async () => {
            if (!registerForm.username || !registerForm.password) {
                ElementPlus.ElMessage.warning('请输入用户名和密码');
                return;
            }
            
            if (registerForm.password !== registerForm.confirmPassword) {
                ElementPlus.ElMessage.warning('两次输入的密码不一致');
                return;
            }
            
            loading.value = true;
            try {
                await axios.post('/public-api/accounts/register', {
                    username: registerForm.username,
                    password: registerForm.password,
                    email: registerForm.username + '@example.com' // 添加一个默认邮箱，因为后端API需要邮箱字段
                });
                
                ElementPlus.ElMessage.success('注册成功，请登录');
                activeTab.value = 'login';
                loginForm.username = registerForm.username;
                loginForm.password = '';
                
                // 清空注册表单
                registerForm.username = '';
                registerForm.password = '';
                registerForm.confirmPassword = '';
            } catch (error) {
                console.error('注册失败', error);
                ElementPlus.ElMessage.error(error.response?.data?.detail || '注册失败');
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
        };
        
        // 加载对话列表
        const loadConversations = async () => {
            try {
                console.log("开始加载对话列表...");
                const response = await http.get('/api/qa/conversations'); // 移除末尾斜杠
                console.log("对话列表响应:", response);
                conversations.value = response.data;
                return true;
            } catch (error) {
                console.error('获取对话列表失败', error);
                console.error('请求URL:', '/api/qa/conversations/');
                console.error('错误状态:', error.response?.status);
                console.error('错误详情:', error.response?.data);
                ElementPlus.ElMessage.error('获取对话列表失败: ' + (error.response?.data?.detail || error.message));
                return false;
            }
        };
        
        // 加载文档列表
        const loadDocuments = async () => {
            try {
                console.log("开始加载文档列表...");
                const response = await http.get('/api/documents'); // 移除末尾斜杠
                console.log("文档列表响应:", response);
                documents.value = response.data;
                return true;
            } catch (error) {
                console.error('获取文档列表失败', error);
                console.error('请求URL:', '/api/documents');
                console.error('错误状态:', error.response?.status);
                console.error('错误详情:', error.response?.data);
                ElementPlus.ElMessage.error('获取文档列表失败: ' + (error.response?.data?.detail || error.message));
                return false;
            }
        };
        
        // 选择对话
        const selectConversation = async (conversation) => {
            console.log("选择对话:", conversation);
            // 先清空当前选择，确保UI完全刷新
            selectedConversation.value = null;
            
            // 使用setTimeout确保DOM更新
            setTimeout(async () => {
                try {
                    console.log("获取对话详情，ID:", conversation.id);
                    const response = await http.get(`/api/qa/conversations/${conversation.id}`);
                    console.log("对话详情响应:", response.data);
                    
                    // 设置消息列表
                    messages.value = response.data.messages || [];
                    console.log("设置消息列表:", messages.value);
                    
                    // 设置选中的对话（使用API返回的完整对话对象）
                    selectedConversation.value = {
                        id: response.data.id,
                        title: response.data.title,
                        created_at: response.data.created_at,
                        updated_at: response.data.updated_at
                    };
                    console.log("设置选中对话:", selectedConversation.value);
                    
                    // 滚动到底部
                    await nextTick();
                    scrollToBottom();
                } catch (error) {
                    console.error('获取对话详情失败', error);
                    ElementPlus.ElMessage.error('获取对话详情失败');
                }
            }, 100);
        };
        
        // 创建新对话
        const createNewConversation = () => {
            console.log("创建新对话按钮点击");
            newConversationTitle.value = '新对话';
            // 确保对话框可见
            setTimeout(() => {
                newConversationDialogVisible.value = true;
                console.log("新对话对话框显示状态:", newConversationDialogVisible.value);
            }, 100);
        };
        
        // 提交新对话
        const submitNewConversation = async () => {
            if (!newConversationTitle.value.trim()) {
                ElementPlus.ElMessage.warning('请输入对话标题');
                return;
            }
            
            try {
                console.log("创建新对话:", newConversationTitle.value);
                const response = await http.post('/api/qa/conversations', { // 移除末尾斜杠
                    title: newConversationTitle.value
                });
                
                // 添加到对话列表
                conversations.value.unshift(response.data);
                
                // 选择新创建的对话
                selectConversation(response.data);
                
                // 关闭对话框
                newConversationDialogVisible.value = false;
                newConversationTitle.value = '';
            } catch (error) {
                console.error('创建对话失败', error);
                ElementPlus.ElMessage.error('创建对话失败');
            }
        };
        
        // 删除对话
        const deleteConversation = async (conversationId) => {
            console.log("尝试删除对话，ID:", conversationId);
            
            // 显示确认对话框
            ElementPlus.ElMessageBox.confirm(
                '确定要删除这个对话吗？删除后将无法恢复。',
                '删除确认',
                {
                    confirmButtonText: '确定删除',
                    cancelButtonText: '取消',
                    type: 'warning',
                }
            ).then(async () => {
                // 用户确认删除
                try {
                    console.log("确认删除对话，ID:", conversationId);
                    await http.delete(`/api/qa/conversations/${conversationId}`);
                    
                    // 从列表中移除
                    conversations.value = conversations.value.filter(c => c.id !== conversationId);
                    
                    // 如果删除的是当前选中的对话，清空选择
                    if (selectedConversation.value && selectedConversation.value.id === conversationId) {
                        selectedConversation.value = null;
                        messages.value = [];
                    }
                    
                    ElementPlus.ElMessage.success('对话已删除');
                } catch (error) {
                    console.error('删除对话失败', error);
                    ElementPlus.ElMessage.error('删除对话失败');
                }
            }).catch(() => {
                // 用户取消删除
                console.log("用户取消删除对话");
                ElementPlus.ElMessage.info('已取消删除');
            });
        };
        
        // 滚动到消息底部
        const scrollToBottom = async () => {
            await nextTick();
            const container = document.querySelector('.messages-container');
            if (container) {
                container.scrollTop = container.scrollHeight;
            }
        };
        
        // 更新对话列表
        const updateConversationList = () => {
            const updatedConv = conversations.value.find(c => c.id === selectedConversation.value.id);
            if (updatedConv) {
                updatedConv.updated_at = new Date().toISOString();
                // 将该对话移到顶部
                conversations.value = [
                    updatedConv,
                    ...conversations.value.filter(c => c.id !== selectedConversation.value.id)
                ];
            }
        };
        
        // 主消息发送函数
        const sendMessage = async () => {
            console.log("发送消息按钮点击", selectedConversation.value);
            if (!newMessage.value.trim()) {
                console.log("消息内容为空，不发送");
                return;
            }
            
            if (!selectedConversation.value || !selectedConversation.value.id) {
                console.error("未选择对话或对话ID不存在");
                ElementPlus.ElMessage.error('请先选择一个对话');
                return;
            }
            
            // 根据模式选择发送方式
            if (useStreamingMode.value) {
                sendMessageStream();
            } else {
                sendMessageNormal();
            }
        };
        
        // 普通模式发送消息
        const sendMessageNormal = async () => {
            const messageContent = newMessage.value;
            newMessage.value = '';
            sendingMessage.value = true;
            
            try {
                console.log("发送消息到对话(普通模式)，ID:", selectedConversation.value.id, "内容:", messageContent);
                
                // 添加用户消息
                messages.value.push({
                    id: Date.now(), // 临时ID
                    content: messageContent,
                    message_type: 'user',
                    created_at: new Date().toISOString(),
                    referenced_documents: []
                });
                
                // 调用API
                const response = await http.post(`/api/qa/conversations/${selectedConversation.value.id}/messages`, {
                    content: messageContent
                });
                console.log("发送消息响应:", response.data);
                
                // 添加助手回复
                messages.value.push(response.data);
                
                // 滚动到底部
                scrollToBottom();
                
                // 更新对话列表
                updateConversationList();
            } catch (error) {
                console.error('发送消息失败', error);
                ElementPlus.ElMessage.error('发送消息失败');
                
                // 恢复消息内容
                newMessage.value = messageContent;
            } finally {
                sendingMessage.value = false;
            }
        };
        
        // 流式模式发送消息
        const sendMessageStream = () => {
            const messageContent = newMessage.value;
            newMessage.value = '';
            sendingMessage.value = true;
            
            try {
                console.log("发送消息到对话(流式模式)，ID:", selectedConversation.value.id, "内容:", messageContent);
                
                // 添加用户消息
                messages.value.push({
                    id: Date.now(), // 临时ID
                    content: messageContent,
                    message_type: 'user',
                    created_at: new Date().toISOString(),
                    referenced_documents: []
                });
                
                // 创建一个空的助手消息占位符
                let assistantMessage = {
                    id: Date.now() + 1, // 临时ID
                    content: '', // 空内容，将逐渐填充
                    message_type: 'assistant',
                    created_at: new Date().toISOString(),
                    referenced_documents: []
                };
                
                // 添加到消息列表
                messages.value.push(assistantMessage);
                currentStreamingMessage.value = assistantMessage;
                
                // 滚动到底部
                scrollToBottom();
                
                // 更新对话列表
                updateConversationList();
                
                // 创建SSE连接
                const url = `${API_BASE_URL}/api/qa/conversations/${selectedConversation.value.id}/messages/stream`;
                const params = new URLSearchParams({
                    content: messageContent,
                    token: token.value, // 添加认证令牌作为查询参数
                    model: selectedModel.value // 添加选择的模型
                });
                console.log("创建流式连接，参数:", params.toString());
                const eventSource = new EventSource(`${url}?${params}`);
                
                // 处理消息事件
                eventSource.onmessage = (event) => {
                    try {
                        console.log("收到SSE事件:", event);
                        const data = JSON.parse(event.data);
                        console.log("解析的流式数据:", data);
                        
                        // 增量更新消息内容
                        if (data.answer_delta) {
                            console.log(`收到增量内容: "${data.answer_delta}"`);
                            
                            // 解决Vue响应式更新问题：创建对象的副本并重新赋值
                            const updatedContent = assistantMessage.content + data.answer_delta;
                            
                            // 创建消息的完整副本
                            const updatedMessage = {
                                ...assistantMessage,
                                content: updatedContent
                            };
                            
                            // 如果有引用文档，更新
                            if (data.referenced_documents && data.referenced_documents.length > 0) {
                                updatedMessage.referenced_documents = data.referenced_documents;
                            }
                            
                            // 更新消息ID (从临时ID更新为服务器分配的ID)
                            if (data.message_id) {
                                updatedMessage.id = data.message_id;
                            }
                            
                            // 如果返回了模型信息，显示
                            if (data.model && !assistantMessage.model) {
                                updatedMessage.model = data.model;
                            }
                            
                            // 找到消息在数组中的索引
                            const messageIndex = messages.value.findIndex(m => m.id === assistantMessage.id);
                            if (messageIndex !== -1) {
                                // 替换整个消息对象，触发Vue响应式更新
                                messages.value.splice(messageIndex, 1, updatedMessage);
                                
                                // 更新当前流式消息的引用
                                assistantMessage = updatedMessage;
                                currentStreamingMessage.value = updatedMessage;
                            }
                            
                            // 滚动到底部
                            nextTick(() => {
                                scrollToBottom();
                            });
                        }
                        
                        // 如果是最后一条消息，关闭连接
                        if (data.finished) {
                            eventSource.close();
                            sendingMessage.value = false;
                            currentStreamingMessage.value = null;
                            console.log("流式传输完成");
                        }
                        
                        // 处理错误
                        if (data.error) {
                            console.error("流式响应错误:", data.error_message);
                            ElementPlus.ElMessage.error(`生成回复出错: ${data.error_message}`);
                            eventSource.close();
                            sendingMessage.value = false;
                            currentStreamingMessage.value = null;
                        }
                    } catch (err) {
                        console.error("解析流式数据出错:", err);
                        eventSource.close();
                        sendingMessage.value = false;
                    }
                };
                
                // 处理错误
                eventSource.onerror = (err) => {
                    console.error("流式连接错误:", err);
                    ElementPlus.ElMessage.error('流式连接出错');
                    eventSource.close();
                    sendingMessage.value = false;
                    currentStreamingMessage.value = null;
                };
                
                // 添加open事件处理
                eventSource.onopen = () => {
                    console.log("SSE连接已打开，准备接收数据");
                };
                
            } catch (error) {
                console.error('发送流式消息失败', error);
                ElementPlus.ElMessage.error('发送流式消息失败');
                
                // 恢复消息内容
                newMessage.value = messageContent;
                sendingMessage.value = false;
                currentStreamingMessage.value = null;
            }
        };
        
        // 上传文档相关
        const openUploadDialog = () => {
            console.log("打开上传对话框按钮点击");
            // 清空表单
            uploadForm.title = '';
            uploadForm.description = '';
            uploadForm.file = null;
            // 确保对话框可见
            setTimeout(() => {
                uploadDialogVisible.value = true;
                console.log("上传对话框显示状态:", uploadDialogVisible.value);
            }, 100);
        };
        
        const beforeUpload = (file) => {
            const validTypes = ['application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', 'text/plain'];
            const isValidType = validTypes.includes(file.type);
            const isLt10M = file.size / 1024 / 1024 < 10;
            
            if (!isValidType) {
                ElementPlus.ElMessage.error('只能上传PDF、DOCX或TXT文件');
                return false;
            }
            
            if (!isLt10M) {
                ElementPlus.ElMessage.error('文件大小不能超过10MB');
                return false;
            }
            
            uploadForm.file = file;
            return false; // 阻止自动上传
        };
        
        const handleFileUpload = (options) => {
            uploadForm.file = options.file;
        };
        
        const uploadDocument = async () => {
            if (!uploadForm.title) {
                ElementPlus.ElMessage.warning('请输入文档标题');
                return;
            }
            
            if (!uploadForm.file) {
                ElementPlus.ElMessage.warning('请选择文件');
                return;
            }
            
            uploading.value = true;
            
            try {
                const formData = new FormData();
                
                // 创建document_in JSON字符串
                const documentIn = {
                    title: uploadForm.title,
                    description: uploadForm.description || ''
                };
                
                // 添加document_in作为JSON字符串
                formData.append('document_in', JSON.stringify(documentIn));
                formData.append('file', uploadForm.file);
                
                console.log("上传文档:", uploadForm.title, documentIn);
                await http.post('/api/documents/', formData, { // 添加末尾斜杠
                    headers: {
                        'Content-Type': 'multipart/form-data'
                    }
                });
                
                ElementPlus.ElMessage.success('文档上传成功');
                uploadDialogVisible.value = false;
                
                // 重新加载文档列表
                loadDocuments();
            } catch (error) {
                console.error('上传文档失败', error);
                ElementPlus.ElMessage.error(error.response?.data?.detail || '上传文档失败');
            } finally {
                uploading.value = false;
            }
        };
        
        // 文档检索
        const searchDocuments = async () => {
            if (!searchQuery.value.trim()) {
                ElementPlus.ElMessage.warning('请输入搜索关键词');
                return;
            }
            
            searching.value = true;
            
            try {
                console.log("执行文档检索:", searchQuery.value);
                const response = await http.post('/api/qa/retrieve', { // 移除末尾斜杠
                    query: searchQuery.value,
                    top_k: 5
                });
                
                searchResults.value = response.data.results;
                
                if (searchResults.value.length === 0) {
                    ElementPlus.ElMessage.info('没有找到相关文档');
                }
            } catch (error) {
                console.error('搜索文档失败', error);
                ElementPlus.ElMessage.error('搜索文档失败');
            } finally {
                searching.value = false;
            }
        };
        
        // 监听消息框键盘事件
        const handleMessageKeydown = (event) => {
            if (event.key === 'Enter' && event.ctrlKey) {
                event.preventDefault();
                sendMessage();
            }
        };
        
        return {
            isLoggedIn,
            userInfo,
            loading,
            activeTab,
            loginForm,
            registerForm,
            conversations,
            selectedConversation,
            messages,
            newMessage,
            sendingMessage,
            documents,
            uploadDialogVisible,
            uploading,
            uploadForm,
            newConversationDialogVisible,
            newConversationTitle,
            searchQuery,
            searchResults,
            searching,
            useStreamingMode,  // 新增：流式模式控制
            selectedModel,     // 新增：模型选择
            modelOptions,      // 新增：模型选项
            
            // 方法
            handleLogin,
            handleRegister,
            handleLogout,
            selectConversation,
            createNewConversation,
            submitNewConversation,
            deleteConversation,
            sendMessage,
            openUploadDialog,
            beforeUpload,
            handleFileUpload,
            uploadDocument,
            searchDocuments,
            handleMessageKeydown,
            formatDate
        };
    }
});

// 等待DOM加载完成并确保Element Plus完全加载
document.addEventListener('DOMContentLoaded', function() {
    // 确保Element Plus已加载
    setTimeout(() => {
        // 注册ElementPlus组件库
        if (ElementPlus) {
            app.use(ElementPlus);
            console.log('ElementPlus组件已注册');
        } else {
            console.error('ElementPlus未加载');
        }
        
        // 挂载Vue应用
        app.mount('#app');
        console.log('Vue应用已挂载');
    }, 300);
});