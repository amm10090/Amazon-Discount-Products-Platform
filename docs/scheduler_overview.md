# 调度器系统概述 (Scheduler Overview)

## 1. 引言

本项目的调度器系统负责自动化执行各种数据采集和维护任务，例如爬取亚马逊畅销商品、优惠券信息、更新现有商品数据以及从CJ平台获取数据等。该系统基于 `APScheduler` 库构建，并提供了一套管理和监控任务的机制。

核心实现位于 `src/core/service_scheduler.py` 文件中的 `SchedulerManager` 类。

## 2. 核心组件

*   **`SchedulerManager` (`src/core/service_scheduler.py`)**:
    *   调度系统的核心管理器，采用单例模式。
    *   负责初始化 `APScheduler` 实例、加载配置、添加/删除/管理任务、启动/停止调度器。
    *   处理任务执行逻辑的分派。
*   **`APScheduler` (`apscheduler` 库)**:
    *   底层的任务调度库，支持多种触发器（Cron, Interval）。
    *   负责根据预定时间执行任务。
*   **`SQLAlchemyJobStore` (`apscheduler.jobstores.sqlalchemy`)**:
    *   `APScheduler` 的任务存储后端。
    *   将任务定义持久化存储在 SQLite 数据库 (`data/db/scheduler.db`) 中，确保即使应用重启，任务也不会丢失。
*   **`JobHistoryModel` (`models/scheduler.py`)**:
    *   SQLAlchemy 模型，用于在数据库 (`scheduler.db` 的 `job_history` 表) 中记录每个任务的执行历史（开始时间、结束时间、状态、采集数量、错误信息等）。
*   **任务执行函数**:
    *   `SchedulerManager._execute_job`: 任务执行的入口点，负责记录历史和调用 `_crawl_products`。
    *   `SchedulerManager._crawl_products`: 根据任务类型调用具体的爬虫或更新器逻辑。
*   **具体爬虫/更新器脚本**:
    *   `src/core/collect_products.py` (`crawl_bestseller_products`, `crawl_coupon_products`)
    *   `src/core/product_updater.py` (`ProductUpdater`)
    *   `src/core/discount_scraper_mt.py` (`CouponScraperMT`)
    *   `src/core/cj_products_crawler.py` (`CJProductsCrawler`)

## 3. 工作流程

1.  **初始化**:
    *   当 FastAPI 应用启动时（通过 `lifespan` 管理），`SchedulerManager` 实例被创建。
    *   加载配置（默认或从 `config/app.yaml`，但目前主要依赖默认和环境变量）。
    *   设置日志记录器 (`logs/scheduler.log`)。
    *   初始化 SQLite 数据库连接和 `JobHistoryModel` 表。
    *   初始化 `APScheduler` 实例，配置 `SQLAlchemyJobStore` 和时区。
    *   从配置文件或默认配置中加载预定义的任务并添加到调度器。
    *   启动 `APScheduler`。
2.  **任务添加**:
    *   可以通过 FastAPI 接口 (`/api/scheduler/jobs`) 或在初始化时从配置添加新任务。
    *   支持 `cron`（定时，如每天几点）和 `interval`（间隔，如每隔几小时）类型的触发器。
    *   任务配置包括 ID、类型、爬虫类型、最大采集数量以及特定于触发器的参数（小时、分钟等）。
    *   可以为特定任务类型（如 `update`, `discount`）传递额外的配置参数 (`updater_config`, `discount_config`)。
3.  **任务执行**:
    *   `APScheduler` 根据任务的触发器时间自动调用 `SchedulerManager._execute_job`。
    *   `_execute_job` 记录任务开始执行的历史信息到 `job_history` 表。
    *   `_execute_job` 调用 `_crawl_products`，并传递任务类型、最大数量和额外配置。
    *   `_crawl_products` 根据 `crawler_type`：
        *   如果是 `update`，实例化并运行 `ProductUpdater`。
        *   如果是 `cj`，实例化并运行 `CJProductsCrawler`。
        *   如果是 `discount`，实例化并运行 `CouponScraperMT`。
        *   如果是 `bestseller` 或 `coupon`，调用 `collect_products.py` 中的相应函数。
        *   如果是 `all`，分别调用 `bestseller` 和 `coupon` 的逻辑。
    *   具体的爬虫/更新器执行其逻辑（访问亚马逊网站、调用 API、处理数据、更新数据库等）。
4.  **任务记录**:
    *   任务执行完成后（无论成功或失败），`_execute_job` 更新 `job_history` 表中的记录，包括结束时间、最终状态、采集到的项目数量（如果成功）或错误信息（如果失败）。
5.  **状态管理与监控**:
    *   FastAPI 提供了（尽管未在 OpenAPI schema 中公开）用于管理和监控的 API 端点：
        *   获取调度器状态 (`/api/scheduler/status`)。
        *   获取所有任务列表 (`/api/scheduler/jobs`)。
        *   暂停/恢复任务 (`/api/scheduler/jobs/{job_id}/pause`, `/api/scheduler/jobs/{job_id}/resume`)。
        *   删除任务 (`/api/scheduler/jobs/{job_id}`)。
        *   获取任务执行历史 (`/api/scheduler/jobs/{job_id}/history`)。
        *   立即执行某个任务 (`/api/scheduler/jobs/{job_id}/execute`)。
        *   更新调度器时区 (`/api/scheduler/timezone`)。
    *   前端界面 (`frontend/pages/scheduler.py`) 调用这些 API，提供可视化的管理界面。

## 4. 支持的任务类型 (`crawler_type`)

*   `bestseller`: 爬取亚马逊畅销商品列表。
*   `coupon`: 爬取亚马逊带有优惠券的商品列表（注意：可能与 `discount` 功能重叠或为旧实现）。
*   `update`: 使用 `ProductUpdater` 更新数据库中现有商品的详细信息（价格、库存、评分等），采用优先级策略。
*   `discount`: 使用 `CouponScraperMT`（多线程 Selenium 爬虫）抓取或更新特定商品的优惠券信息。
*   `cj`: 使用 `CJProductsCrawler` 从 CJ Affiliate 平台爬取商品信息。
*   `all`: 同时执行 `bestseller` 和 `coupon` 类型的爬取任务。

## 5. 配置方式

*   **默认配置**: `SchedulerManager` 内部定义了一组默认任务和配置。
*   **环境变量**:
    *   `AMAZON_ACCESS_KEY`, `AMAZON_SECRET_KEY`, `AMAZON_PARTNER_TAG`: PA-API 凭证。
    *   `SCHEDULER_DB_PATH`: 指定调度器数据库文件路径。
    *   `SCHEDULER_TIMEZONE`: 设置调度器时区 (默认 'Asia/Shanghai')。
    *   `CRAWLER_*`: 控制爬虫行为的参数（如 `CRAWLER_HEADLESS`, `CRAWLER_BATCH_SIZE`）。
    *   `DISCOUNT_SCRAPER_*`: 控制 `CouponScraperMT` 行为的参数（如 `DISCOUNT_SCRAPER_THREADS`, `DISCOUNT_SCRAPER_UPDATE_INTERVAL`）。
    *   `APP_LOG_DIR`: 指定日志文件存放目录。
*   **API 添加/修改**: 可以通过 API 动态添加、修改或删除任务。
*   **(潜在) 配置文件**: `config/app.yaml` 可以用于配置，但当前 `SchedulerManager` 初始化逻辑似乎未直接使用它来加载任务。

## 6. 数据持久化

*   **任务定义**: 通过 `SQLAlchemyJobStore` 存储在 `data/db/scheduler.db` 文件的 `apscheduler_jobs` 表中。这确保了即使应用程序重启，已安排的任务也会被保留和恢复。
*   **任务历史**: 通过 `JobHistoryModel` 存储在 `data/db/scheduler.db` 文件的 `job_history` 表中。

## 7. 管理方式

*   **API**: 提供了一组 RESTful API 用于编程方式管理调度器和任务。
*   **前端界面 (`frontend/pages/scheduler.py`)**: 基于 Streamlit 构建，提供了一个用户友好的界面来：
    *   查看调度器状态和任务列表。
    *   添加、暂停、恢复、删除任务。
    *   立即触发任务执行。
    *   查看任务的执行历史。
    *   过滤和排序任务。
    *   管理调度器时区和启停。

## 8. 日志记录

*   调度器相关的日志信息记录在 `logs/scheduler.log` 文件中。
*   任务执行过程中的详细日志（由 `TaskLogContext` 或具体爬虫/更新器生成）通常记录在应用的主日志文件 (`logs/app.*.log`) 或特定爬虫的日志文件中（如 `logs/coupon_scraper_mt.log`）。

## 9. 开发者文档

### 9.1 添加新的任务类型

1.  **创建任务逻辑脚本**: 在 `src/core` 或相关目录下创建一个新的 Python 文件，实现新任务的具体逻辑。这个脚本应该包含一个主要的异步函数或类来执行任务。
2.  **修改 `SchedulerManager._crawl_products`**: 在 `src/core/service_scheduler.py` 中的 `_crawl_products` 静态方法内，添加一个新的 `elif` 条件来处理你的新 `crawler_type`。
    ```python
    elif crawler_type == "your_new_type":
        # 导入你的新任务脚本
        from src.core.your_new_task_module import YourNewTaskRunner

        # 实例化并执行任务
        runner = YourNewTaskRunner(config_params) # 假设你的任务需要配置
        result = await runner.run(max_items)
        task_log.success(f"新任务类型 '{crawler_type}' 完成，结果: {result}")
        return result
    ```
3.  **更新前端界面 (可选)**: 如果希望在前端界面 (`frontend/pages/scheduler.py`) 中能选择和配置这个新任务类型，需要：
    *   修改 `task_categories` 字典，添加新的分类或在现有分类中加入新的 `crawler_type`。
    *   更新相关的文本翻译（在 `frontend/i18n/` 目录下）。
    *   如果新任务有独特的配置参数，可能需要在任务添加表单中添加相应的输入字段，并在提交时将这些参数打包到 `job_config` 中（可能放在一个特定的键下，如 `your_new_task_config`）。

### 9.2 配置参数传递

*   在通过 API 或前端添加任务时，可以为特定任务类型（当前主要是 `update` 和 `discount`）指定额外的配置字典。
*   这些配置字典会被打包并作为 `_execute_job` 的最后一个参数 (`config_params`) 传递。
*   `_execute_job` 会将这个 `config_params` 字典原样传递给 `_crawl_products`。
*   `_crawl_products` 在调用具体的任务逻辑（如 `ProductUpdater`, `CouponScraperMT` 或你添加的新任务）时，会将这个 `config_params` 字典传递过去。
*   具体的任务逻辑脚本需要负责解析这个字典，并使用其中的配置项。
*   **注意**: 当前实现中，`discount_config` 是直接从 `config_params` 中提取的（如果 `crawler_type` 是 `discount`），而 `updater_config` 也是类似处理。在添加新任务类型时，需要决定如何组织和传递其特定配置。

### 9.3 日志记录 (`TaskLogContext`)

*   建议在长时间运行的任务逻辑（如 `_crawl_products` 或具体的爬虫/更新器函数/方法）中使用 `TaskLogContext` 上下文管理器（位于 `src/core/product_updater.py`，但可以考虑将其移到更通用的位置）。
    ```python
    from src.core.product_updater import TaskLogContext

    async def my_task_logic(max_items, config):
        async with TaskLogContext(task_id="MY_TASK_ID") as task_log:
            task_log.info(f"任务开始，最大数量: {max_items}")
            try:
                # ... 执行任务 ...
                result = ...
                task_log.success(f"任务成功完成，结果: {result}")
                return result
            except Exception as e:
                task_log.error(f"任务失败: {str(e)}")
                raise
    ```
*   `TaskLogContext` 会自动记录任务的开始、成功结束或失败结束，并计算执行时间。它使用 Loguru 进行结构化日志记录。

### 9.4 错误处理

*   `_execute_job` 函数包裹了对 `_crawl_products` 的调用，并捕获所有异常。
*   如果 `_crawl_products` 或其调用的具体任务逻辑抛出异常，该异常会被捕获，任务状态会被记录为 'failed'，错误信息会被存储到 `job_history` 表中。
*   具体的任务逻辑脚本内部也应该进行适当的错误处理和日志记录，但最终未被捕获的异常会由 `_execute_job` 处理。

### 9.5 依赖与环境

*   确保新添加的任务脚本所需的任何库都已添加到项目的依赖中（如 `requirements.txt` 或 `pyproject.toml`）。
*   如果任务需要特定的环境变量，确保在 `.env.example` 中记录，并在部署时配置相应的 `.env` 文件。 