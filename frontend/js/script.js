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
        const newConversationDialogVisible = ref(false);
        const newConversationTitle = ref('');
        
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
                console.error('请求URL:', '/api/documents/');
                console.error('错误状态:', error.response?.status);
                console.error('错误详情:', error.response?.data);
                ElementPlus.ElMessage.error('获取文档列表失败: ' + (error.response?.data?.detail || error.message));
                return false;
            }
        };
        
        // 选择对话
        const selectConversation = async (conversation) => {
            selectedConversation.value = conversation;
            try {
                console.log("获取对话详情，ID:", conversation.id);
                const response = await http.get(`/api/qa/conversations/${conversation.id}`); // 移除末尾斜杠
                messages.value = response.data.messages;
                
                // 滚动到底部
                await nextTick();
                const container = document.querySelector('.messages-container');
                if (container) {
                    container.scrollTop = container.scrollHeight;
                }
            } catch (error) {
                console.error('获取对话详情失败', error);
                ElementPlus.ElMessage.error('获取对话详情失败');
            }
        };
        
        // 创建新对话
        const createNewConversation = () => {
            newConversationTitle.value = '新对话 - ' + new Date().toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
            newConversationDialogVisible.value = true;
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
            try {
                console.log("删除对话，ID:", conversationId);
                await http.delete(`/api/qa/conversations/${conversationId}`); // 移除末尾斜杠
                
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
        };
        
        // 发送消息
        const sendMessage = async () => {
            if (!newMessage.value.trim() || !selectedConversation.value) {
                return;
            }
            
            const messageContent = newMessage.value;
            newMessage.value = '';
            sendingMessage.value = true;
            
            try {
                console.log("发送消息到对话，ID:", selectedConversation.value.id);
                const response = await http.post(`/api/qa/conversations/${selectedConversation.value.id}/messages`, { // 移除末尾斜杠
                    content: messageContent
                });
                
                // 更新消息列表
                messages.value.push({
                    id: Date.now(), // 临时ID
                    content: messageContent,
                    message_type: 'user',
                    created_at: new Date().toISOString(),
                    referenced_documents: []
                });
                
                // 添加助手回复
                messages.value.push(response.data);
                
                // 滚动到底部
                await nextTick();
                const container = document.querySelector('.messages-container');
                if (container) {
                    container.scrollTop = container.scrollHeight;
                }
                
                // 更新对话列表中的更新时间
                const updatedConv = conversations.value.find(c => c.id === selectedConversation.value.id);
                if (updatedConv) {
                    updatedConv.updated_at = new Date().toISOString();
                    // 将该对话移到顶部
                    conversations.value = [
                        updatedConv,
                        ...conversations.value.filter(c => c.id !== selectedConversation.value.id)
                    ];
                }
            } catch (error) {
                console.error('发送消息失败', error);
                ElementPlus.ElMessage.error('发送消息失败');
                
                // 恢复消息内容
                newMessage.value = messageContent;
            } finally {
                sendingMessage.value = false;
            }
        };
        
        // 上传文档相关
        const openUploadDialog = () => {
            uploadDialogVisible.value = true;
            uploadForm.title = '';
            uploadForm.description = '';
            uploadForm.file = null;
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
                formData.append('title', uploadForm.title);
                if (uploadForm.description) {
                    formData.append('description', uploadForm.description);
                }
                formData.append('file', uploadForm.file);
                
                console.log("上传文档:", uploadForm.title);
                await http.post('/api/documents', formData, { // 移除末尾斜杠
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
        // 挂载Vue应用
        app.mount('#app');
        console.log('Vue应用已挂载');
    }, 300);
});