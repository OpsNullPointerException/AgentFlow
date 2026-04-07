-- PostgreSQL全文搜索支持SQL脚本
-- 运行此脚本为DocumentChunk表添加全文搜索能力

-- 1. 如果需要中文分词支持，安装pg_jieba扩展（可选）
-- CREATE EXTENSION IF NOT EXISTS pg_jieba;

-- 2. 创建触发器函数，自动维护tsvector列
CREATE OR REPLACE FUNCTION update_document_chunk_tsv()
RETURNS TRIGGER AS $$
BEGIN
    -- 使用中文分词器生成tsvector
    -- 如果没安装中文扩展，可以用默认的english或simple
    NEW.tsv := to_tsvector('chinese', NEW.content);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- 3. 为已有数据生成tsvector（一次性）
UPDATE documents_documentchunk
SET tsv = to_tsvector('chinese', content)
WHERE tsv IS NULL;

-- 4. 创建GIN索引加速全文搜索查询
-- 这是全文搜索性能的关键！
CREATE INDEX CONCURRENTLY idx_document_chunk_tsv
ON documents_documentchunk USING GIN (tsv);

-- 5. 创建触发器，新插入或更新时自动维护tsvector
DROP TRIGGER IF EXISTS trg_update_document_chunk_tsv ON documents_documentchunk;
CREATE TRIGGER trg_update_document_chunk_tsv
BEFORE INSERT OR UPDATE ON documents_documentchunk
FOR EACH ROW
EXECUTE FUNCTION update_document_chunk_tsv();

-- 验证查询
-- SELECT id, title, ts_rank_cd(tsv, plainto_tsquery('chinese', '能耗')) AS rank
-- FROM documents_documentchunk
-- WHERE tsv @@ plainto_tsquery('chinese', '能耗')
-- ORDER BY rank DESC LIMIT 10;
