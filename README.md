# Job Spider - 招聘数据爬虫系统

企业级招聘网站数据采集系统，支持智联招聘、前程无忧、Boss直聘等主流招聘平台。

## 功能特性

- 🔍 多平台职位搜索
- 📊 薪资数据分析
- 🔄 定时自动爬取
- 📈 数据导出（CSV/Excel）
- 🛡️ 完善的反爬策略

## 快速开始

### 环境要求

- Python 3.11+
- pip

### 安装

```bash
# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate  # Linux/Mac
# .venv\Scripts\activate  # Windows

# 安装依赖
pip install -r requirements.txt
```

### 使用

```bash
# 爬取智联招聘数据
python -m job_spider crawl zhilian --keyword "Python开发" --city "深圳"

# 查看统计
python -m job_spider stats

# 导出数据
python -m job_spider export --format excel --output output/jobs.xlsx
```

## 项目结构

```
job-spider/
├── config/          # 配置文件
├── src/job_spider/  # 源代码
│   ├── core/        # 核心模块
│   ├── spiders/     # 爬虫实现
│   ├── middleware/  # 中间件
│   ├── storage/     # 存储层
│   └── pipeline/    # 数据管道
├── data/            # 数据存储
├── output/          # 导出文件
├── logs/            # 日志
└── wiki/            # 项目文档
```

## 支持的招聘网站

| 网站 | 状态 | 反爬等级 |
|------|------|----------|
| 智联招聘 | ✅ 已支持 | 低 |
| 前程无忧 | 🚧 开发中 | 中 |
| Boss直聘 | 📋 计划中 | 高 |

## 开发

```bash
# 安装开发依赖
pip install -r requirements-dev.txt

# 运行测试
pytest

# 代码格式化
black src/
isort src/
```

## License

MIT
