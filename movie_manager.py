#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
影视文件管理和种子下载系统
"""

import os
import json
import shutil
import requests
import logging
from pathlib import Path
from typing import List, Dict, Optional, Tuple
from urllib.parse import urljoin
from flask import Flask, render_template, request, jsonify, redirect, url_for
import re
import time
import hashlib
import base64
import random
import string
import threading
from difflib import SequenceMatcher
from datetime import datetime, timedelta

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

app = Flask(__name__)
app.secret_key = 'movie_manager_secret_key_2024'

class MovieManager:
    def __init__(self):
        self.config_file = "movie_manager_config.json"
        self.data_file = "movie_manager_data.json"

        # 默认配置
        self.tmdb_api_key = None
        self.tmdb_base_url = "https://api.themoviedb.org/3"
        self.qb_host = None
        self.qb_username = None
        self.qb_password = None
        self.processed_files = {}  # 存储已处理的文件路径映射
        self.removed_torrents = {}  # 存储已移除种子的记录

        # 路径配置
        self.movie_path = ""
        self.exclude_dirs = []
        self.torrent_path = ""

        # TMDB API频率限制
        self.last_tmdb_request_time = 0
        self.tmdb_request_interval = 0.25  # 250ms间隔，每秒最多4次请求

        # 分类配置文件路径
        self.category_config_file = os.path.join(os.path.dirname(__file__), 'category_config.yaml')

        # 分类配置
        self.category_config = self.load_category_config()

        # 高级功能配置
        self.skip_verify = False  # 跳过校验
        self.auto_start = True    # 自动开始
        self.monitor_interval = 30  # 状态监控间隔（秒）
        self.enable_monitoring = False  # 启用状态监控

        # 种子状态跟踪
        self.pending_torrents = {}  # 待校验的种子 {hash: {tag, add_time, path}}
        self.monitoring_thread = None
        self.monitoring_stop_event = threading.Event()

        # 加载配置和数据
        self.load_config()
        self.load_data()

    def load_category_config(self):
        """加载分类配置"""
        try:
            if os.path.exists(self.category_config_file):
                import yaml
                with open(self.category_config_file, 'r', encoding='utf-8') as f:
                    config = yaml.safe_load(f)
                logger.info(f"从文件加载分类配置: {self.category_config_file}")
                return config
            else:
                logger.info("分类配置文件不存在，使用默认配置")
                return self.get_default_category_config()
        except Exception as e:
            logger.error(f"加载分类配置失败: {e}，使用默认配置")
            return self.get_default_category_config()

    def get_default_category_config(self):
        """获取默认分类配置"""
        config = {
            'movie': {
                '中国动画电影': {
                    'genre_ids': '16',
                    'original_language': 'zh,cn,bo,za'
                },
                '日韩动画电影': {
                    'genre_ids': '16',
                    'original_language': 'ja,ko'
                },
                '欧美动画电影': {
                    'genre_ids': '16'
                },
                '恐怖电影': {
                    'genre_ids': '27'
                },
                '华语电影': {
                    'original_language': 'zh,cn,bo,za'
                },
                '日韩电影': {
                    'original_language': 'ja,ko'
                },
                '欧美电影': {}
            },
            'tv': {
                '中国动漫': {
                    'genre_ids': '16',
                    'origin_country': 'CN,TW,HK'
                },
                '儿童动漫': {
                    'genre_ids': '10762'
                },
                '日韩动漫': {
                    'genre_ids': '16',
                    'origin_country': 'JP,KR'
                },
                '欧美动漫': {
                    'genre_ids': '16'
                },
                '中国纪录片': {
                    'genre_ids': '99',
                    'original_language': 'zh,cn,bo,za'
                },
                '外国纪录片': {
                    'genre_ids': '99'
                },
                '中国综艺': {
                    'genre_ids': '10764,10767',
                    'original_language': 'zh,cn,bo,za'
                },
                '日韩综艺': {
                    'genre_ids': '10764,10767',
                    'original_language': 'ja,ko'
                },
                '欧美综艺': {
                    'genre_ids': '10764,10767'
                },
                '国产剧': {
                    'origin_country': 'CN,TW,HK'
                },
                '日韩剧': {
                    'original_language': 'ja,ko'
                },
                '欧美剧': {}
            }
        }
        return config

    def save_category_config(self, config_text: str) -> bool:
        """保存分类配置到文件"""
        try:
            import yaml
            # 验证YAML格式
            config = yaml.safe_load(config_text)

            # 验证配置结构
            if not isinstance(config, dict) or 'movie' not in config or 'tv' not in config:
                raise ValueError("配置格式错误：必须包含movie和tv两个顶级分类")

            # 保存到文件
            with open(self.category_config_file, 'w', encoding='utf-8') as f:
                f.write(config_text)

            # 重新加载配置
            self.category_config = config

            logger.info(f"分类配置保存成功: {self.category_config_file}")
            return True

        except yaml.YAMLError as e:
            logger.error(f"YAML格式错误: {e}")
            return False
        except Exception as e:
            logger.error(f"保存分类配置失败: {e}")
            return False

    def get_category_config_text(self) -> str:
        """获取当前分类配置的YAML文本"""
        try:
            if os.path.exists(self.category_config_file):
                with open(self.category_config_file, 'r', encoding='utf-8') as f:
                    return f.read()
            else:
                # 返回默认配置的YAML格式
                return self.get_default_config_yaml()
        except Exception as e:
            logger.error(f"读取分类配置失败: {e}")
            return self.get_default_config_yaml()

    def get_default_config_yaml(self) -> str:
        """获取默认配置的YAML文本"""
        return '''####### 配置说明 #######
# 1. 该配置文件用于配置电影和电视剧的分类策略，配置后程序会按照配置的分类策略名称进行分类，配置文件采用yaml格式，需要严格附合语法规则
# 2. 配置文件中的一级分类名称：`movie`、`tv` 为固定名称不可修改，二级名称同时也是目录名称，会按先后顺序匹配，匹配后程序会按这个名称建立二级目录
# 3. 支持的分类条件：
#   `original_language` 语种，具体含义参考下方字典
#   `production_countries` 国家或地区（电影）、`origin_country` 国家或地区（电视剧），具体含义参考下方字典
#   `genre_ids` 内容类型，具体含义参考下方字典
#   themoviedb 详情API返回的其它一级字段
# 4. 配置多项条件时需要同时满足，一个条件需要匹配多个值是使用`,`分隔

# 配置电影的分类策略
movie:
  中国动画电影:
    genre_ids: '16'
    original_language: 'zh,cn,bo,za'
  日韩动画电影:
    genre_ids: '16'
    original_language: 'ja,ko'
  欧美动画电影:
    genre_ids: '16'
  恐怖电影:
    genre_ids: '27'
  华语电影:
    original_language: 'zh,cn,bo,za'
  日韩电影:
    original_language: 'ja,ko'
  欧美电影:

# 配置电视剧的分类策略
tv:
  中国动漫:
    genre_ids: '16'
    # 匹配 origin_country 国家，CN是中国大陆，TW是中国台湾，HK是中国香港
    origin_country: 'CN,TW,HK'
  儿童动漫:
    genre_ids: '10762'
  日韩动漫:
    genre_ids: '16'
    # 匹配 origin_country 国家，JP是日本
    origin_country: 'JP,KR'
  欧美动漫:
    genre_ids: '16'
  中国纪录片:
    genre_ids: '99'
    original_language: 'zh,cn,bo,za'
  外国纪录片:
    genre_ids: '99'
  中国综艺:
    genre_ids: '10764,10767'
    original_language: 'zh,cn,bo,za'
  日韩综艺:
    genre_ids: '10764,10767'
    original_language: 'ja,ko'
  欧美综艺:
    genre_ids: '10764,10767'
  国产剧:
    origin_country: 'CN,TW,HK'
  日韩剧:
    original_language: 'ja,ko'
  欧美剧:

## genre_ids 内容类型 字典，注意部分中英文是不一样的
#	28	Action / 动作
#	12	Adventure / 冒险
#	16	Animation / 动画
#	35	Comedy / 喜剧
#	80	Crime / 犯罪
#	99	Documentary / 纪录
#	18	Drama / 剧情
#	10751	Family / 家庭
#	14	Fantasy / 奇幻
#	36	History / 历史
#	27	Horror / 恐怖
#	10402	Music / 音乐
#	9648	Mystery / 悬疑
#	10749	Romance / 爱情
#	878	Science Fiction / 科幻
#	10770	TV Movie / 电视电影
#	53	Thriller / 惊悚
#	10752	War / 战争
#	37	Western / 西部
#	10762	Kids / 儿童
#	10764	Reality / 真人秀
#	10767	Talk / 脱口秀

## original_language 语种 字典
#	zh	中文
#	cn	中文
#	en	英语
#	ja	日语
#	ko	朝鲜语/韩语
#	fr	法语
#	de	德语
#	es	西班牙语
#	it	意大利语
#	ru	俄语
#	pt	葡萄牙语
#	hi	印地语
#	ar	阿拉伯语
#	th	泰语
#	vi	越南语

## origin_country/production_countries 国家地区 字典
#	CN	中国内地
#	TW	中国台湾
#	HK	中国香港
#	JP	日本
#	KR	韩国
#	US	美国
#	GB	英国
#	FR	法国
#	DE	德国
#	IT	意大利
#	ES	西班牙
#	RU	俄罗斯
#	IN	印度
#	TH	泰国
#	VN	越南
'''

    def match_category(self, tmdb_data):
        """根据TMDB数据匹配分类"""
        media_type = tmdb_data.get('media_type', 'movie')

        # 获取对应媒体类型的配置
        if media_type == 'tv':
            categories = self.category_config.get('tv', {})
        else:
            categories = self.category_config.get('movie', {})

        logger.info(f"开始匹配分类，媒体类型: {media_type}")

        # 按顺序匹配分类
        for category_name, conditions in categories.items():
            if self.check_conditions(tmdb_data, conditions):
                logger.info(f"匹配成功: {category_name}")
                return category_name

        # 如果没有匹配到，返回默认分类
        default_category = "欧美剧" if media_type == 'tv' else "欧美电影"
        logger.info(f"未匹配到特定分类，使用默认分类: {default_category}")
        return default_category

    def check_conditions(self, tmdb_data, conditions):
        """检查是否满足分类条件"""
        for key, value in conditions.items():
            if not value:  # 空条件，匹配所有
                continue

            if key == 'genre_ids':
                # 检查类型ID
                required_genres = [int(x.strip()) for x in value.split(',')]
                tmdb_genres = tmdb_data.get('genre_ids', [])
                if not any(genre in tmdb_genres for genre in required_genres):
                    return False

            elif key == 'original_language':
                # 检查语言
                required_langs = [x.strip().lower() for x in value.split(',')]
                tmdb_lang = tmdb_data.get('original_language', '').lower()
                if tmdb_lang not in required_langs:
                    return False

            elif key == 'origin_country':
                # 检查国家（电视剧）
                required_countries = [x.strip().upper() for x in value.split(',')]
                tmdb_countries = tmdb_data.get('origin_country', [])
                if not any(country in tmdb_countries for country in required_countries):
                    return False

            elif key == 'production_countries':
                # 检查制作国家（电影）
                required_countries = [x.strip().upper() for x in value.split(',')]
                tmdb_countries = [c.get('iso_3166_1', '') for c in tmdb_data.get('production_countries', [])]
                if not any(country in tmdb_countries for country in required_countries):
                    return False

        return True

    def load_config(self):
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    config = json.load(f)

                self.tmdb_api_key = config.get('tmdb_api_key')
                self.qb_host = config.get('qb_host')
                self.qb_username = config.get('qb_username')
                self.qb_password = config.get('qb_password')

                # 加载路径配置
                self.movie_path = config.get('movie_path', '')
                self.exclude_dirs = config.get('exclude_dirs', [])
                self.torrent_path = config.get('torrent_path', '')

                # 加载高级功能配置
                self.skip_verify = config.get('skip_verify', False)
                self.auto_start = config.get('auto_start', True)
                self.monitor_interval = config.get('monitor_interval', 30)
                self.enable_monitoring = config.get('enable_monitoring', False)

                logger.info(f"配置文件加载成功: {self.config_file}")
                logger.info(f"TMDB API: {'已配置' if self.tmdb_api_key else '未配置'}")
                logger.info(f"qBittorrent: {'已配置' if self.qb_host else '未配置'}")
                logger.info(f"高级功能: 跳过校验={'开启' if self.skip_verify else '关闭'}, "
                           f"状态监控={'开启' if self.enable_monitoring else '关闭'}")
            else:
                logger.info("配置文件不存在，等待用户首次配置")
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")

    def save_config(self):
        """保存配置文件"""
        try:
            config = {
                'tmdb_api_key': self.tmdb_api_key,
                'qb_host': self.qb_host,
                'qb_username': self.qb_username,
                'qb_password': self.qb_password,
                'movie_path': self.movie_path,
                'exclude_dirs': self.exclude_dirs,
                'torrent_path': self.torrent_path,
                'skip_verify': self.skip_verify,
                'auto_start': self.auto_start,
                'monitor_interval': self.monitor_interval,
                'enable_monitoring': self.enable_monitoring,
                'last_updated': time.time()
            }

            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)

            logger.info(f"配置文件保存成功: {self.config_file}")
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")

    def load_data(self):
        """加载数据文件"""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)

                self.processed_files = data.get('processed_files', {})
                self.removed_torrents = data.get('removed_torrents', {})

                logger.info(f"数据文件加载成功: {self.data_file}")
                logger.info(f"已处理文件数量: {len(self.processed_files)}")
                logger.info(f"已移除种子记录数量: {len(self.removed_torrents)}")
            else:
                logger.info("数据文件不存在，将创建新的数据文件")
        except Exception as e:
            logger.error(f"加载数据文件失败: {e}")
            self.processed_files = {}
            self.removed_torrents = {}

    def save_data(self):
        """保存数据文件"""
        try:
            data = {
                'processed_files': self.processed_files,
                'removed_torrents': self.removed_torrents,
                'last_updated': time.time(),
                'total_processed': len(self.processed_files),
                'total_removed_torrents': len(self.removed_torrents)
            }

            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info(f"数据文件保存成功: {self.data_file}, 已处理文件: {len(self.processed_files)}, 已移除种子记录: {len(self.removed_torrents)}")
        except Exception as e:
            logger.error(f"保存数据文件失败: {e}")

    def add_removed_torrent_record(self, torrent_info: Dict, matched_info: Dict) -> None:
        """添加已移除种子的记录"""
        try:
            # 创建种子的唯一标识
            torrent_key = self.generate_torrent_key(torrent_info, matched_info)

            # 记录详细信息
            record = {
                'torrent_name': torrent_info.get('name', ''),
                'torrent_title': torrent_info.get('title', ''),
                'matched_filename': matched_info.get('name', ''),
                'similarity': matched_info.get('similarity', 0),
                'match_type': matched_info.get('match_type', ''),
                'download_path': matched_info.get('download_path', ''),
                'removed_time': time.time(),
                'removed_count': self.removed_torrents.get(torrent_key, {}).get('removed_count', 0) + 1
            }

            self.removed_torrents[torrent_key] = record
            logger.info(f"记录已移除种子: {torrent_info.get('name', '')} -> {matched_info.get('name', '')} (相似度: {matched_info.get('similarity', 0):.2f})")

            # 保存数据
            self.save_data()

        except Exception as e:
            logger.error(f"记录移除种子失败: {e}")

    def generate_torrent_key(self, torrent_info: Dict, matched_info: Dict) -> str:
        """生成种子的唯一标识键"""
        try:
            # 使用种子标题和匹配文件名生成唯一键
            torrent_title = torrent_info.get('title', '').lower().strip()
            matched_name = matched_info.get('name', '').lower().strip()
            similarity = round(matched_info.get('similarity', 0), 2)

            # 创建组合键
            key = f"{torrent_title}|{matched_name}|{similarity}"
            return key

        except Exception as e:
            logger.error(f"生成种子键失败: {e}")
            return f"unknown_{time.time()}"

    def is_torrent_removed(self, torrent_info: Dict, matched_info: Dict) -> bool:
        """检查种子是否已被记录为移除"""
        try:
            torrent_key = self.generate_torrent_key(torrent_info, matched_info)
            return torrent_key in self.removed_torrents

        except Exception as e:
            logger.error(f"检查种子移除状态失败: {e}")
            return False

    def apply_removed_torrent_records(self, matched_torrents: List[Dict]) -> None:
        """应用已移除种子记录，自动标记匹配的种子为移除状态"""
        try:
            auto_removed_count = 0

            for match in matched_torrents:
                torrent_info = match.get('torrent', {})
                matched_file_info = {
                    'name': match.get('matched_filename', ''),
                    'similarity': match.get('similarity', 0),
                    'match_type': match.get('matched_file', {}).get('match_type', ''),
                    'download_path': match.get('matched_file', {}).get('download_path', '')
                }

                # 检查是否在已移除记录中
                if self.is_torrent_removed(torrent_info, matched_file_info):
                    match['selected'] = False  # 标记为未选择（即移除状态）
                    auto_removed_count += 1

                    # 更新移除记录的计数
                    torrent_key = self.generate_torrent_key(torrent_info, matched_file_info)
                    if torrent_key in self.removed_torrents:
                        self.removed_torrents[torrent_key]['removed_count'] += 1
                        self.removed_torrents[torrent_key]['last_auto_removed'] = time.time()

                    logger.info(f"自动移除种子（基于历史记录）: {torrent_info.get('name', '')} -> {matched_file_info.get('name', '')}")
                else:
                    match['selected'] = True  # 默认选择

            if auto_removed_count > 0:
                logger.info(f"基于历史记录自动移除了 {auto_removed_count} 个种子")
                # 保存更新的数据
                self.save_data()

        except Exception as e:
            logger.error(f"应用移除种子记录失败: {e}")

    def scan_directory(self, path: str, exclude_dirs: List[str] = None) -> Dict:
        """扫描目录下的所有文件和文件夹（只扫描第一层）"""
        if exclude_dirs is None:
            exclude_dirs = []

        result = {
            'files': [],
            'directories': [],
            'total_files': 0,
            'total_dirs': 0
        }

        try:
            if not os.path.exists(path):
                logger.error(f"路径不存在: {path}")
                return result

            # 只扫描第一层，不递归遍历子目录
            items = os.listdir(path)

            for item in items:
                item_path = os.path.join(path, item)

                # 跳过排除的目录
                if item in exclude_dirs:
                    continue

                if os.path.isfile(item_path):
                    # 处理文件
                    file_info = {
                        'name': item,
                        'path': item_path,
                        'size': os.path.getsize(item_path),
                        'type': 'file',
                        'extension': os.path.splitext(item)[1].lower()
                    }
                    result['files'].append(file_info)
                    result['total_files'] += 1

                elif os.path.isdir(item_path):
                    # 处理目录 - 只获取目录名称，不遍历内部
                    dir_info = {
                        'name': item,
                        'path': item_path,
                        'type': 'directory'
                    }
                    result['directories'].append(dir_info)
                    result['total_dirs'] += 1

        except Exception as e:
            logger.error(f"扫描目录失败: {e}")

        return result
    
    def search_tmdb(self, query: str, media_type: str = 'multi', max_retries: int = 3) -> List[Dict]:
        """通过TMDB API搜索影视作品（带频率限制和重试机制）"""
        if not self.tmdb_api_key:
            logger.error("TMDB API密钥未设置")
            return []

        # 频率限制：确保请求间隔
        current_time = time.time()
        time_since_last_request = current_time - self.last_tmdb_request_time

        if time_since_last_request < self.tmdb_request_interval:
            sleep_time = self.tmdb_request_interval - time_since_last_request
            logger.debug(f"TMDB频率限制，等待 {sleep_time:.2f} 秒")
            time.sleep(sleep_time)

        self.last_tmdb_request_time = time.time()

        url = f"{self.tmdb_base_url}/search/{media_type}"
        params = {
            'api_key': self.tmdb_api_key,
            'query': query,
            'language': 'zh-CN'
        }

        logger.info(f"搜索TMDB: {query}")

        # 重试机制
        for attempt in range(max_retries):
            try:
                response = requests.get(url, params=params, timeout=15)
                response.raise_for_status()

                data = response.json()
                results = data.get('results', [])
                logger.info(f"TMDB搜索结果: 找到 {len(results)} 个匹配项")
                return results

            except requests.exceptions.Timeout:
                logger.warning(f"TMDB搜索超时 (尝试 {attempt + 1}/{max_retries}): {query}")
                if attempt < max_retries - 1:
                    time.sleep(1 * (attempt + 1))  # 递增等待时间

            except requests.exceptions.SSLError as e:
                logger.warning(f"TMDB SSL错误 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(2 * (attempt + 1))  # SSL错误等待更长时间

            except requests.exceptions.ConnectionError as e:
                logger.warning(f"TMDB连接错误 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(1 * (attempt + 1))

            except requests.exceptions.RequestException as e:
                logger.warning(f"TMDB请求失败 (尝试 {attempt + 1}/{max_retries}): {e}")
                if attempt < max_retries - 1:
                    time.sleep(1 * (attempt + 1))

            except Exception as e:
                logger.error(f"TMDB搜索异常: {e}")
                break  # 其他异常不重试

        logger.error(f"TMDB搜索最终失败，已重试 {max_retries} 次: {query}")
        return []
    
    def extract_title_from_filename(self, filename: str) -> str:
        """从文件名中提取影视作品标题（优化版）"""
        # 移除文件扩展名
        name = os.path.splitext(filename)[0]
        original_name = name

        logger.debug(f"开始提取标题: {filename}")

        # 预处理: 先移除常见的视频质量标识和发布组信息
        patterns = [
            r'\b(1080p|720p|480p|4K|2160p|UHD)\b',
            r'\b(BluRay|BDRip|DVDRip|WEBRip|HDTV|WEB-DL|HDRip)\b',
            r'\b(x264|x265|H264|H265|HEVC|AVC)\b',
            r'\b(AC3|DTS|AAC|FLAC|MP3|Atmos)\b',
            r'\b(REMUX|REPACK|PROPER|INTERNAL)\b',
            r'\b(HDR|SDR|Dolby|Vision)\b',
            r'\b(COMPLETE|BLURAY|GLiMMER|MKiEDb)\b',
            r'\{(.*?)\}',  # 移除花括号内容
            r'-[A-Z0-9_]+$',  # 移除结尾的发布组标识（包含下划线）
            r'__[A-Z0-9_]+$',  # 移除双下划线开头的发布组标识
        ]

        for pattern in patterns:
            name = re.sub(pattern, '', name, flags=re.IGNORECASE)

        # 清理多余的空格和特殊字符
        name = re.sub(r'\s+', ' ', name).strip()

        logger.debug(f"预处理后: {name}")

        # 规则0: 如果名称是下划线连接的，提取第一个下划线之前的内容
        if '_' in name and not re.search(r'\[.*\]', name):  # 排除中括号格式
            first_underscore_pos = name.find('_')
            before_underscore = name[:first_underscore_pos].strip()
            if before_underscore and len(before_underscore) >= 2:
                # 将.替换为空格
                extracted_title = before_underscore.replace('.', ' ').strip()
                logger.info(f"规则0-下划线分割提取: '{filename}' -> '{extracted_title}'")
                return extracted_title

        # 规则1: 有[]的直接提取中括号内的内容（只有位于开头才生效）
        if name.startswith('['):
            bracket_match = re.search(r'^\[([^\]]+)\]', name)
            if bracket_match:
                bracket_content = bracket_match.group(1).strip()

                # 检查中括号内容是否包含中文
                if re.search(r'[\u4e00-\u9fff]', bracket_content):
                    # 规则1.2: 如果[]内的中文包含季度信息，提取季度之前的内容
                    season_pattern = r'第([一二三四五六七八九十\d]+)季'
                    season_match = re.search(season_pattern, bracket_content)
                    if season_match:
                        before_season = bracket_content.split('第')[0].strip()
                        if before_season:
                            logger.info(f"规则1.2-中括号中文季度提取: '{filename}' -> '{before_season}'")
                            return before_season

                    # 规则1.1: 如果[]内的中文存在空格或者.，则提取分割前的第一部分内容
                    if ' ' in bracket_content or '.' in bracket_content:
                        # 按空格和点分割，取第一部分
                        first_part = re.split(r'[ .]', bracket_content)[0].strip()
                        if first_part and re.search(r'[\u4e00-\u9fff]', first_part):
                            logger.info(f"规则1.1-中括号中文分割提取: '{filename}' -> '{first_part}'")
                            return first_part

                extracted_title = bracket_content
                logger.info(f"规则1-中括号提取: '{filename}' -> '{extracted_title}'")
                return extracted_title

        # 规则2: 第一个.之前是中英文交杂或纯中文，提取第一个.之前的所有中文
        first_dot_pos = name.find('.')
        if first_dot_pos > 0:
            before_first_dot = name[:first_dot_pos]
            # 检查是否包含中文字符
            if re.search(r'[\u4e00-\u9fff]', before_first_dot):
                # 提取所有中文字符
                chinese_chars = re.findall(r'[\u4e00-\u9fff]+', before_first_dot)
                if chinese_chars:
                    chinese_text = ''.join(chinese_chars)

                    # 规则2.1: 如果中文内容包含"之"，则提取"之"之前的内容
                    if '之' in chinese_text:
                        before_zhi = chinese_text.split('之')[0].strip()
                        if before_zhi:
                            logger.info(f"规则2.1-中文'之'字提取: '{filename}' -> '{before_zhi}'")
                            return before_zhi

                    # 规则2.2: 如果中文中包含季度信息，提取季度之前的内容
                    season_pattern = r'第([一二三四五六七八九十\d]+)季'
                    season_match = re.search(season_pattern, chinese_text)
                    if season_match:
                        before_season = chinese_text.split('第')[0].strip()
                        if before_season:
                            logger.info(f"规则2.2-中文季度提取: '{filename}' -> '{before_season}'")
                            return before_season

                    extracted_title = chinese_text
                    logger.info(f"规则2-中文提取: '{filename}' -> '{extracted_title}'")
                    return extracted_title

        # 规则3: 英文名称中时间、季度同时存在的处理
        # 季度匹配：支持.S数字 和 空格S数字 格式
        season_match_dot = re.search(r'\.S\d+', name, re.IGNORECASE)
        season_match_space = re.search(r'\sS\d+', name, re.IGNORECASE)
        season_match = season_match_dot or season_match_space

        # 年份匹配：支持.年份 和 空格年份 格式
        year_match_dot = re.search(r'\.(\d{4})', name)
        year_match_space = re.search(r'\s(\d{4})', name)
        year_match = year_match_dot or year_match_space

        if season_match and year_match:
            season_pos = season_match.start()
            year_pos = year_match.start()

            # 如果时间处于S季度之前，则提取时间之前的全部内容
            if year_pos < season_pos:
                before_year = name[:year_pos]
                # 如果是.分割，则把.替换成空格
                if '.' in before_year:
                    extracted_title = before_year.replace('.', ' ').strip()
                else:
                    extracted_title = before_year.strip()
                logger.info(f"规则3-时间在季度前提取: '{filename}' -> '{extracted_title}'")
                return extracted_title

            # 如果S季度处于时间之前，则提取S季度之前的全部内容
            else:
                before_season = name[:season_pos]
                # 如果是.分割，则把.替换成空格
                if '.' in before_season:
                    extracted_title = before_season.replace('.', ' ').strip()
                else:
                    extracted_title = before_season.strip()
                logger.info(f"规则3-季度在时间前提取: '{filename}' -> '{extracted_title}'")
                return extracted_title

        # 规则3.1: 纯英文 + S季度（无时间），提取S之前的所有内容
        elif season_match and not year_match:
            season_pos = season_match.start()
            before_season = name[:season_pos]
            # 如果是.分割，则把.替换成空格
            if '.' in before_season:
                extracted_title = before_season.replace('.', ' ').strip()
            else:
                extracted_title = before_season.strip()
            logger.info(f"规则3.1-纯季度提取: '{filename}' -> '{extracted_title}'")
            return extracted_title

        # 规则4: 纯英文 + 时间（无季度），提取时间之前的所有内容
        elif year_match and not season_match:
            year_pos = year_match.start()
            before_year = name[:year_pos]
            # 如果是.分割，则把.替换成空格
            if '.' in before_year:
                extracted_title = before_year.replace('.', ' ').strip()
            else:
                extracted_title = before_year.strip()
            logger.info(f"规则4-纯时间提取: '{filename}' -> '{extracted_title}'")
            return extracted_title

        # 规则5: 其他情况按原逻辑处理
        logger.debug(f"使用原逻辑处理: {filename}")

        # 移除年份（其他标识已在预处理中移除）
        name = re.sub(r'\b\d{4}\b', '', name)

        # # 特殊处理：保留圆括号中的年份
        # year_in_brackets = re.search(r'\((\d{4})\)', name)
        # if year_in_brackets:
        #     year = year_in_brackets.group(1)
        #     name = re.sub(r'\([^)]*\)', '', name)  # 移除所有圆括号内容
        #     name = f"{name.strip()} ({year})"  # 重新添加年份
        # else:
        #     name = re.sub(r'\([^)]*\)', '', name)  # 移除圆括号内容

        # 清理多余的空格和特殊字符
        name = re.sub(r'[._-]+', ' ', name)
        name = re.sub(r'\s+', ' ', name).strip()

        # 如果提取结果为空或太短，使用原始文件名
        if len(name.strip()) < 2:
            logger.warning(f"提取的标题太短，使用原始文件名: {original_name}")
            name = original_name

        logger.info(f"标题提取完成: '{filename}' -> '{name}'")
        return name

    def extract_title_from_torrent_filename(self, filename: str) -> str:
        """从种子文件名中提取影视作品标题（简化处理）"""
        # 移除文件扩展名
        name = os.path.splitext(filename)[0]
        original_name = name

        logger.debug(f"开始提取种子标题: {filename}")

        # 种子文件特殊预处理：去除第一个中括号及其后面的点
        bracket_match = re.search(r'^\[([^\]]+)\]\.?', name)
        if bracket_match:
            # 移除第一个中括号及其内容，以及可能紧跟的点
            name = name[bracket_match.end():].strip()
            logger.debug(f"移除第一个中括号及后面的点后: {name}")

        # 如果处理后的名称为空或太短，使用原始文件名
        if len(name.strip()) < 2:
            logger.warning(f"种子预处理后标题太短，使用原始文件名: {original_name}")
            name = original_name

        # 简单清理：移除多余的空格
        name = re.sub(r'\s+', ' ', name).strip()

        logger.info(f"种子标题提取完成: '{filename}' -> '{name}'")
        return name

    def create_category_folder(self, base_path: str, category_name: str) -> str:
        """创建类目文件夹"""
        # 清理文件夹名称，移除不合法字符
        safe_name = re.sub(r'[<>:"/\\|?*]', '', category_name)
        folder_path = os.path.join(base_path, safe_name)
        
        try:
            os.makedirs(folder_path, exist_ok=True)
            logger.info(f"创建文件夹: {folder_path}")
            return folder_path
        except Exception as e:
            logger.error(f"创建文件夹失败: {e}")
            return None
    
    def move_file_to_category(self, file_path: str, category_folder: str) -> Optional[str]:
        """移动文件到类目文件夹"""
        try:
            filename = os.path.basename(file_path)
            new_path = os.path.join(category_folder, filename)

            # 如果目标文件已存在，添加序号
            counter = 1
            while os.path.exists(new_path):
                name, ext = os.path.splitext(filename)
                new_filename = f"{name}_{counter}{ext}"
                new_path = os.path.join(category_folder, new_filename)
                counter += 1

            shutil.move(file_path, new_path)
            logger.info(f"移动文件: {file_path} -> {new_path}")
            return new_path

        except Exception as e:
            logger.error(f"移动文件失败: {e}")
            return None

    def move_directory_to_category(self, dir_path: str, category_folder: str) -> Optional[str]:
        """移动文件夹到类目文件夹"""
        try:
            dirname = os.path.basename(dir_path)
            new_path = os.path.join(category_folder, dirname)

            # 如果目标文件夹已存在，添加序号
            counter = 1
            while os.path.exists(new_path):
                new_dirname = f"{dirname}_{counter}"
                new_path = os.path.join(category_folder, new_dirname)
                counter += 1

            shutil.move(dir_path, new_path)
            logger.info(f"移动文件夹: {dir_path} -> {new_path}")
            return new_path

        except Exception as e:
            logger.error(f"移动文件夹失败: {e}")
            return None

    def scan_torrent_files(self, torrent_path: str) -> List[Dict]:
        """扫描种子文件夹"""
        torrent_files = []

        try:
            if not os.path.exists(torrent_path):
                logger.error(f"种子文件夹不存在: {torrent_path}")
                return torrent_files

            for root, dirs, files in os.walk(torrent_path):
                for file in files:
                    if file.lower().endswith('.torrent'):
                        file_path = os.path.join(root, file)
                        torrent_info = {
                            'name': file,
                            'path': file_path,
                            'size': os.path.getsize(file_path),
                            'title': self.extract_title_from_torrent_filename(file)
                        }
                        torrent_files.append(torrent_info)

        except Exception as e:
            logger.error(f"扫描种子文件失败: {e}")

        return torrent_files

    def scan_all_movie_files(self, movie_path: str) -> List[Dict]:
        """扫描影视文件夹下的所有文件，分析文件与父文件夹的关系"""
        match_candidates = []

        if not movie_path or not os.path.exists(movie_path):
            logger.warning(f"影视文件夹路径无效: {movie_path}")
            return match_candidates

        logger.info(f"开始扫描影视文件夹: {movie_path}")

        # 预处理：获取影视目录的直接子目录名称
        direct_subdirs = set()
        try:
            for item in os.listdir(movie_path):
                item_path = os.path.join(movie_path, item)
                if os.path.isdir(item_path):
                    direct_subdirs.add(item)
            logger.info(f"影视目录直接子目录: {list(direct_subdirs)} (共{len(direct_subdirs)}个)")
        except Exception as e:
            logger.error(f"获取直接子目录失败: {e}")
            direct_subdirs = set()

        try:
            for root, dirs, files in os.walk(movie_path):
                # 只处理影视文件（常见的视频文件扩展名）
                video_extensions = {'.mp4', '.mkv', '.avi', '.mov', '.wmv', '.flv', '.webm', '.m4v', '.ts', '.m2ts', '.rmvb', '.rm', '.3gp', '.f4v'}
                video_files = [f for f in files if os.path.splitext(f.lower())[1] in video_extensions]

                if video_files:
                    # 获取当前目录信息
                    current_dir = root
                    parent_dir_name = os.path.basename(current_dir)
                    grandparent_dir = os.path.dirname(current_dir)

                    # 跳过根目录（影视文件夹本身）
                    if current_dir == movie_path:
                        continue

                    # 分析第一个视频文件与父文件夹的相似性
                    first_video = video_files[0]
                    # 直接使用原始文件名和文件夹名，不进行复杂的标题提取
                    file_name_clean = os.path.splitext(first_video)[0].lower()  # 去除扩展名
                    folder_name_clean = parent_dir_name.lower()

                    # 计算相似度
                    similarity = SequenceMatcher(None, file_name_clean, folder_name_clean).ratio()

                    logger.debug(f"分析文件夹: {parent_dir_name}")
                    logger.debug(f"  第一个文件: {first_video}")
                    logger.debug(f"  文件名(去扩展名): {file_name_clean}")
                    logger.debug(f"  文件夹名: {folder_name_clean}")
                    logger.debug(f"  相似度: {similarity:.2f}")

                    # 根据相似性确定匹配策略
                    if similarity > 0.6:  # 文件名与父文件夹相似
                        # 匹配父文件夹名称，下载到父文件夹的父目录
                        download_path = grandparent_dir
                        match_type = "folder_similar"
                        logger.debug(f"  策略: 文件与文件夹相似，下载到父目录: {download_path}")
                    else:  # 文件名与父文件夹不相似
                        # 匹配父文件夹名称，下载到父文件夹内
                        download_path = current_dir
                        match_type = "folder_different"
                        logger.debug(f"  策略: 文件与文件夹不相似，下载到文件夹内: {download_path}")

                    # 关键判断：检查当前文件夹是否为影视目录的直接子目录
                    if parent_dir_name in direct_subdirs:
                        # 文件夹是直接子目录，使用文件名进行匹配
                        for video_file in video_files:
                            file_name_without_ext = os.path.splitext(video_file)[0]
                            logger.debug(f"  → 直接子目录，添加文件名: {file_name_without_ext}")
                            match_candidates.append({
                                'name': file_name_without_ext,  # 用于匹配的名称（文件名，去扩展名）
                                'path': current_dir,            # 文件夹路径
                                'download_path': download_path, # 下载路径
                                'type': 'file_match',
                                'match_type': match_type,
                                'similarity_with_file': similarity,
                                'sample_file': video_file,
                                'file_count': len(video_files),
                                'parent_folder': parent_dir_name
                            })
                    else:
                        # 文件夹不是直接子目录，使用文件夹名进行匹配（保持原逻辑）
                        logger.debug(f"  → 非直接子目录，添加文件夹名: {parent_dir_name}")
                        match_candidates.append({
                            'name': parent_dir_name,        # 用于匹配的名称（父文件夹名）
                            'path': current_dir,            # 文件夹路径
                            'download_path': download_path, # 下载路径
                            'type': 'folder_match',
                            'match_type': match_type,
                            'similarity_with_file': similarity,
                            'sample_file': first_video,
                            'file_count': len(video_files)
                        })

        except Exception as e:
            logger.error(f"扫描影视文件夹异常: {e}")

        logger.info(f"扫描完成，找到 {len(match_candidates)} 个匹配候选项")

        # 记录子目录集合和所有文件列表
        logger.info("=" * 60)
        logger.info(f"影视目录直接子目录集合: {sorted(list(direct_subdirs))}")

        # 收集所有文件名
        all_files = []
        for candidate in match_candidates:
            if candidate['type'] == 'file_match':
                all_files.append(candidate['name'])
            else:  # folder_match
                all_files.append(f"[文件夹] {candidate['name']}")

        logger.info(f"所有文件列表 ({len(all_files)} 个): {all_files}")
        logger.info("=" * 60)
        return match_candidates

    def match_torrents_with_files(self, torrent_files: List[Dict]) -> Dict:
        """匹配种子文件与影视文件夹下的所有文件"""
        matched = []
        unmatched = []

        # 获取影视文件夹路径
        movie_path = getattr(self, 'movie_path', '')
        if not movie_path:
            logger.error("影视文件夹路径未配置，无法进行匹配")
            return {'matched': [], 'unmatched': torrent_files}

        # 扫描影视文件夹下的所有文件，获取匹配候选项
        match_candidates = self.scan_all_movie_files(movie_path)

        logger.info(f"开始匹配种子文件: {len(torrent_files)} 个种子, {len(match_candidates)} 个匹配候选项")

        for torrent in torrent_files:
            torrent_title = torrent['title'].lower()
            torrent_name = torrent['name']
            best_match = None
            best_score = 0
            best_filename = ""
            best_candidate = None

            logger.debug(f"匹配种子: {torrent_name} -> 提取标题: {torrent['title']}")

            # 与所有匹配候选项进行匹配
            for candidate in match_candidates:
                folder_name = candidate['name']
                # 直接比较种子标题与原始文件夹名，不使用复杂的标题提取
                folder_name_lower = folder_name.lower()

                # 计算相似度（种子标题已经是简化处理后的）
                similarity = SequenceMatcher(None, torrent_title, folder_name_lower).ratio()

                logger.debug(f"  候选项: {folder_name} (相似度: {similarity:.2f}, 类型: {candidate['match_type']})")

                if similarity > best_score and similarity > 0.6:  # 相似度阈值
                    best_score = similarity
                    best_match = candidate
                    best_filename = folder_name
                    best_candidate = candidate

            if best_match:
                logger.info(f"种子匹配成功: {torrent_name} -> {best_filename} (相似度: {best_score:.2f}, 策略: {best_candidate['match_type']})")

                # 构建匹配文件信息
                matched_file_info = {
                    'name': best_filename,
                    'path': best_candidate['path'],
                    'download_path': best_candidate['download_path'],
                    'type': 'folder_match',
                    'match_type': best_candidate['match_type'],
                    'sample_file': best_candidate['sample_file'],
                    'file_count': best_candidate['file_count']
                }

                matched.append({
                    'torrent': torrent,
                    'matched_file': matched_file_info,
                    'matched_filename': best_filename,
                    'similarity': best_score
                })
            else:
                logger.warning(f"种子未找到匹配: {torrent_name} -> {torrent['title']}")
                unmatched.append(torrent)

        logger.info(f"种子匹配完成 - 匹配成功: {len(matched)}, 未匹配: {len(unmatched)}")

        # 检查已移除种子记录，自动标记为移除
        self.apply_removed_torrent_records(matched)

        # 重新统计应用移除记录后的结果
        selected_count = len([m for m in matched if m.get('selected', True)])
        removed_count = len([m for m in matched if not m.get('selected', True)])

        logger.info(f"应用移除记录后 - 总匹配: {len(matched)}, 已选择: {selected_count}, 已移除: {removed_count}, 未匹配: {len(unmatched)}")

        return {
            'matched': matched,
            'unmatched': unmatched
        }

    def preprocess_torrent_name(self, torrent_name: str) -> str:
        """预处理种子文件名，智能处理中括号和点分割的内容"""
        try:
            # 移除文件扩展名
            name = os.path.splitext(torrent_name)[0]
            original_name = name

            logger.debug(f"开始预处理种子文件名: {torrent_name}")

            # 智能处理：检查是否有多个中括号
            bracket_matches = re.findall(r'\[([^\]]+)\]', name)
            if len(bracket_matches) >= 2:
                # 如果有多个中括号，通常第一个是发布组，第二个是标题
                logger.debug(f"发现多个中括号: {bracket_matches}")

                # 移除第一个中括号（发布组）
                first_bracket = re.search(r'^\[([^\]]+)\]\.?', name)
                if first_bracket:
                    name = name[first_bracket.end():].strip()
                    logger.debug(f"移除第一个中括号后: {name}")

                # 保留后续的中括号内容，它们可能包含重要的标题信息
                # 不再移除第一个点之前的内容，因为可能是重要的标题部分

            else:
                # 只有一个或没有中括号的情况，按原逻辑处理
                bracket_match = re.search(r'^\[([^\]]+)\]\.?', name)
                if bracket_match:
                    name = name[bracket_match.end():].strip()
                    logger.debug(f"移除第一个中括号后: {name}")

                # 如果还有内容，查找第一个点的位置
                first_dot_pos = name.find('.')
                if first_dot_pos > 0:
                    # 检查第一个点之前的内容是否包含中文
                    before_first_dot = name[:first_dot_pos]
                    if not re.search(r'[\u4e00-\u9fff]', before_first_dot):
                        # 如果第一个点之前没有中文，可能是发布组标识，可以移除
                        after_first_dot = name[first_dot_pos + 1:].strip()
                        if after_first_dot:
                            name = after_first_dot
                            logger.debug(f"移除第一个点之前的内容后: {name}")

            # 如果处理后的名称为空或太短，使用原始文件名
            if len(name.strip()) < 2:
                logger.warning(f"预处理后标题太短，使用原始文件名: {original_name}")
                name = original_name

            logger.info(f"种子文件名预处理完成: '{torrent_name}' -> '{name}'")
            return name

        except Exception as e:
            logger.error(f"预处理种子文件名失败: {e}，使用原始文件名")
            return torrent_name

    def determine_category_for_torrent(self, torrent_info: Dict) -> str:
        """根据种子信息确定qBittorrent分类"""
        try:
            # 获取种子标题（这是简化提取的标题）
            torrent_title = torrent_info.get('title', '')
            if not torrent_title:
                logger.warning("种子标题为空，使用默认分类")
                return 'movie_manager'

            # 获取原始种子文件名
            torrent_name = torrent_info.get('name', '')
            if not torrent_name:
                logger.warning("种子文件名为空，使用简化标题")
                search_title = torrent_title
            else:
                # 对原始种子文件名进行高级标题提取
                # 先去掉第一个[]和.之前的内容，然后使用复杂的标题提取规则
                processed_name = self.preprocess_torrent_name(torrent_name)
                search_title = self.extract_title_from_filename(processed_name)
                logger.info(f"种子标题处理: {torrent_name} -> {processed_name} -> {search_title}")

            # 通过TMDB搜索获取内容信息
            tmdb_results = self.search_tmdb(search_title, 'multi')

            if not tmdb_results:
                logger.info(f"TMDB未找到匹配结果: {search_title}，使用默认分类")
                return 'movie_manager'

            # 使用第一个搜索结果
            tmdb_data = tmdb_results[0]

            # 根据TMDB数据匹配分类
            category = self.match_category(tmdb_data)

            logger.info(f"种子分类确定: {search_title} -> {category}")
            return category

        except Exception as e:
            logger.error(f"确定种子分类失败: {e}，使用默认分类")
            return 'movie_manager'

    def generate_random_tag(self, length: int = 10) -> str:
        """生成随机标签"""
        return ''.join(random.choices(string.ascii_letters + string.digits, k=length))

    def qb_get_torrents(self, filter_type: str = "all") -> List[Dict]:
        """获取种子列表"""
        try:
            if not hasattr(self, 'qb_cookies'):
                if not self.qb_login():
                    logger.error("qBittorrent登录失败，无法获取种子列表")
                    return []

            torrents_url = f"{self.qb_host}/api/v2/torrents/info"
            params = {'filter': filter_type}

            response = requests.get(torrents_url, params=params, cookies=self.qb_cookies, timeout=10)
            response.raise_for_status()

            return response.json()

        except Exception as e:
            logger.error(f"获取种子列表失败: {e}")
            return []

    def qb_get_torrent_by_tag(self, tag: str) -> Optional[Dict]:
        """通过标签获取种子信息"""
        try:
            torrents = self.qb_get_torrents()
            for torrent in torrents:
                torrent_tags = torrent.get('tags', '').split(',')
                torrent_tags = [t.strip() for t in torrent_tags if t.strip()]
                if tag in torrent_tags:
                    return torrent
            return None

        except Exception as e:
            logger.error(f"通过标签获取种子失败: {e}")
            return None

    def qb_login(self) -> bool:
        """登录qBittorrent"""
        if not all([self.qb_host, self.qb_username, self.qb_password]):
            logger.error("qBittorrent配置不完整")
            return False

        try:
            login_url = f"{self.qb_host}/api/v2/auth/login"
            data = {
                'username': self.qb_username,
                'password': self.qb_password
            }

            response = requests.post(login_url, data=data, timeout=10)
            response.raise_for_status()

            if response.text == "Ok.":
                self.qb_cookies = response.cookies
                logger.info("qBittorrent登录成功")

                # 检查并创建默认分类
                self.qb_ensure_category('movie_manager')

                return True
            else:
                logger.error("qBittorrent登录失败")
                return False

        except Exception as e:
            logger.error(f"qBittorrent登录异常: {e}")
            return False

    def qb_ensure_category(self, category_name: str = 'movie_manager') -> bool:
        """确保指定分类存在"""
        try:
            # 获取现有分类
            categories_url = f"{self.qb_host}/api/v2/torrents/categories"
            response = requests.get(categories_url, cookies=self.qb_cookies, timeout=10)
            response.raise_for_status()

            categories = response.json()

            if category_name not in categories:
                # 创建分类
                create_url = f"{self.qb_host}/api/v2/torrents/createCategory"
                data = {
                    'category': category_name,
                    'savePath': ''  # 使用默认路径
                }

                response = requests.post(create_url, data=data, cookies=self.qb_cookies, timeout=10)
                response.raise_for_status()

                if response.text == "Ok." or response.status_code == 200:
                    logger.info(f"成功创建qBittorrent分类: {category_name}")
                    return True
                else:
                    logger.warning(f"创建分类失败: {response.text}")
                    return False
            else:
                logger.debug(f"qBittorrent分类{category_name}已存在")
                return True

        except Exception as e:
            logger.warning(f"检查/创建qBittorrent分类异常: {e}")
            return False

    def qb_add_torrent(self, torrent_path: str, download_path: str,
                      category: Optional[str] = None, skip_verify: Optional[bool] = None,
                      auto_start: Optional[bool] = None) -> bool:
        """添加种子到qBittorrent

        Args:
            torrent_path: 种子文件路径
            download_path: 下载路径
            category: qBittorrent分类名称（None时使用默认分类）
            skip_verify: 是否跳过校验（None时使用全局配置）
            auto_start: 是否自动开始（None时使用全局配置）
        """
        try:
            # 检查种子文件是否存在
            if not os.path.exists(torrent_path):
                logger.error(f"种子文件不存在: {torrent_path}")
                return False

            # 检查种子文件大小
            file_size = os.path.getsize(torrent_path)
            if file_size == 0:
                logger.error(f"种子文件为空: {torrent_path}")
                return False

            logger.debug(f"种子文件检查通过: {torrent_path} (大小: {file_size} 字节)")

            if not hasattr(self, 'qb_cookies'):
                if not self.qb_login():
                    logger.error("qBittorrent登录失败，无法添加种子")
                    return False

            add_url = f"{self.qb_host}/api/v2/torrents/add"

            # 使用参数或全局配置
            skip_verify = skip_verify if skip_verify is not None else self.skip_verify
            auto_start = auto_start if auto_start is not None else self.auto_start

            # 生成随机标签用于跟踪
            random_tag = self.generate_random_tag()
            tags = f'auto_added,{random_tag}'

            # 确定分类名称
            qb_category = category if category else 'movie_manager'

            # 确保分类存在
            if not self.qb_ensure_category(qb_category):
                logger.warning(f"无法创建分类 {qb_category}，使用默认分类")
                qb_category = 'movie_manager'
                self.qb_ensure_category(qb_category)

            # 检查下载路径
            logger.debug(f"目标下载路径: {download_path}")
            logger.debug(f"使用分类: {qb_category}")
            logger.debug(f"校验设置: 跳过校验={skip_verify}, 自动开始={auto_start}")

            with open(torrent_path, 'rb') as f:
                files = {'torrents': f}
                data = {
                    'savepath': download_path,
                    'category': qb_category,
                    'tags': tags,
                    'paused': 'true',  # 默认暂停状态
                    'skip_checking': 'true' if skip_verify else 'false'
                }

                logger.debug(f"发送请求到qBittorrent: {add_url}")
                logger.debug(f"请求数据: {data}")

                response = requests.post(
                    add_url,
                    files=files,
                    data=data,
                    cookies=self.qb_cookies,
                    timeout=30
                )

                logger.debug(f"qBittorrent响应状态码: {response.status_code}")
                logger.debug(f"qBittorrent响应内容: {response.text}")

                response.raise_for_status()

                if response.text == "Ok.":
                    logger.info(f"成功添加种子: {torrent_path}")

                    # 添加到待处理队列
                    self.pending_torrents[random_tag] = {
                        'tag': random_tag,
                        'add_time': datetime.now(),
                        'path': torrent_path,
                        'download_path': download_path,
                        'skip_verify': skip_verify,
                        'auto_start': auto_start
                    }

                    # 启动监控（如果启用）
                    if self.enable_monitoring and not self.monitoring_thread:
                        self.start_monitoring()

                    return True
                else:
                    # 详细的错误分析
                    error_msg = response.text.strip()
                    if error_msg == "Fails.":
                        logger.error(f"添加种子失败 - 可能原因:")
                        logger.error(f"  1. 下载路径不存在或无权限: {download_path}")
                        logger.error(f"  2. 种子文件已存在于qBittorrent中")
                        logger.error(f"  3. 种子文件格式错误或损坏")
                        logger.error(f"  4. qBittorrent分类'{qb_category}'不存在")
                        logger.error(f"  5. 磁盘空间不足")
                    else:
                        logger.error(f"添加种子失败: {error_msg}")
                    return False

        except requests.exceptions.RequestException as e:
            logger.error(f"网络请求异常: {e}")
            return False
        except FileNotFoundError as e:
            logger.error(f"种子文件未找到: {e}")
            return False
        except Exception as e:
            logger.error(f"添加种子异常: {e}")
            return False

    def qb_start_torrents(self, hashes: List[str]) -> bool:
        """启动种子"""
        try:
            if not hasattr(self, 'qb_cookies'):
                if not self.qb_login():
                    return False

            start_url = f"{self.qb_host}/api/v2/torrents/resume"
            data = {'hashes': '|'.join(hashes)}

            response = requests.post(start_url, data=data, cookies=self.qb_cookies, timeout=10)
            response.raise_for_status()

            return response.text == "Ok." or response.status_code == 200

        except Exception as e:
            logger.error(f"启动种子失败: {e}")
            return False

    def qb_recheck_torrents(self, hashes: List[str]) -> bool:
        """重新校验种子"""
        try:
            if not hasattr(self, 'qb_cookies'):
                if not self.qb_login():
                    return False

            recheck_url = f"{self.qb_host}/api/v2/torrents/recheck"
            data = {'hashes': '|'.join(hashes)}

            response = requests.post(recheck_url, data=data, cookies=self.qb_cookies, timeout=10)
            response.raise_for_status()

            return response.text == "Ok." or response.status_code == 200

        except Exception as e:
            logger.error(f"重新校验种子失败: {e}")
            return False

    def start_monitoring(self):
        """启动状态监控"""
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            logger.warning("状态监控已在运行")
            return

        self.monitoring_stop_event.clear()
        self.monitoring_thread = threading.Thread(target=self._monitoring_worker, daemon=True)
        self.monitoring_thread.start()
        logger.info("状态监控已启动")

    def stop_monitoring(self):
        """停止状态监控"""
        if self.monitoring_thread and self.monitoring_thread.is_alive():
            self.monitoring_stop_event.set()
            self.monitoring_thread.join(timeout=5)
            logger.info("状态监控已停止")

    def _monitoring_worker(self):
        """状态监控工作线程"""
        logger.info(f"状态监控线程启动，检查间隔: {self.monitor_interval}秒")

        while not self.monitoring_stop_event.is_set():
            try:
                self._check_pending_torrents()
            except Exception as e:
                logger.error(f"状态监控异常: {e}")

            # 等待指定间隔或停止信号
            self.monitoring_stop_event.wait(self.monitor_interval)

        logger.info("状态监控线程已退出")

    def _check_pending_torrents(self):
        """检查待处理种子状态"""
        if not self.pending_torrents:
            return

        completed_tags = []

        for tag, info in self.pending_torrents.items():
            try:
                torrent = self.qb_get_torrent_by_tag(tag)
                if not torrent:
                    # 种子可能被删除或标签丢失
                    logger.warning(f"未找到标签为 {tag} 的种子")
                    completed_tags.append(tag)
                    continue

                state = torrent.get('state', '')
                progress = torrent.get('progress', 0)

                logger.debug(f"种子 {tag} 状态: {state}, 进度: {progress:.2%}")

                # 检查是否可以开始做种
                if state in ['pausedUP', 'stoppedUP'] and progress >= 1.0:
                    # 校验完成且完整
                    if info['auto_start']:
                        torrent_hash = torrent.get('hash')
                        if self.qb_start_torrents([torrent_hash]):
                            logger.info(f"自动启动种子: {info['path']}")
                        else:
                            logger.error(f"启动种子失败: {info['path']}")
                    else:
                        logger.info(f"种子校验完成，等待手动启动: {info['path']}")

                    completed_tags.append(tag)

                elif state in ['error', 'missingFiles']:
                    # 种子出错
                    logger.error(f"种子状态异常: {info['path']}, 状态: {state}")
                    completed_tags.append(tag)

                # 检查超时（24小时）
                elif datetime.now() - info['add_time'] > timedelta(hours=24):
                    logger.warning(f"种子处理超时: {info['path']}")
                    completed_tags.append(tag)

            except Exception as e:
                logger.error(f"检查种子 {tag} 状态失败: {e}")
                completed_tags.append(tag)

        # 清理已完成的种子
        for tag in completed_tags:
            self.pending_torrents.pop(tag, None)

        if completed_tags:
            logger.info(f"清理了 {len(completed_tags)} 个已完成的种子跟踪记录")

# 创建全局实例
movie_manager = MovieManager()

@app.route('/')
def index():
    """主页"""
    return render_template('index.html')

@app.route('/api/scan', methods=['POST'])
def api_scan():
    """扫描目录API"""
    data = request.get_json()
    path = data.get('path', '')
    exclude_dirs = data.get('exclude_dirs', [])

    logger.info(f"API请求 - 扫描目录: {path}, 排除目录: {exclude_dirs}")

    if not path:
        logger.warning("扫描目录API - 路径参数为空")
        return jsonify({'error': '路径不能为空'}), 400

    result = movie_manager.scan_directory(path, exclude_dirs)
    logger.info(f"扫描完成 - 找到 {result['total_files']} 个文件, {result['total_dirs']} 个目录")
    return jsonify(result)

@app.route('/api/search', methods=['POST'])
def api_search():
    """搜索TMDB API"""
    data = request.get_json()
    query = data.get('query', '')

    logger.info(f"API请求 - TMDB搜索: {query}")

    if not query:
        logger.warning("TMDB搜索API - 搜索关键词为空")
        return jsonify({'error': '搜索关键词不能为空'}), 400

    results = movie_manager.search_tmdb(query)
    logger.info(f"TMDB搜索API完成 - 返回 {len(results)} 个结果")
    return jsonify({'results': results})

@app.route('/api/process', methods=['POST'])
def api_process():
    """处理文件/文件夹分类"""
    data = request.get_json()
    base_path = data.get('base_path', '')
    files = data.get('files', [])

    logger.info(f"API请求 - 处理文件分类: 基础路径={base_path}, 项目数量={len(files)}")

    if not base_path or not files:
        logger.warning("处理文件分类API - 参数不完整")
        return jsonify({'error': '参数不完整'}), 400

    results = []
    success_count = 0
    error_count = 0

    for item_info in files:
        item_path = item_info.get('path')
        item_name = item_info.get('name')
        item_type = item_info.get('type', 'file')

        if not item_path or not item_name:
            logger.warning(f"跳过无效项目信息: {item_info}")
            continue

        logger.info(f"开始处理{'文件夹' if item_type == 'directory' else '文件'}: {item_name}")

        # 提取标题并搜索
        title = movie_manager.extract_title_from_filename(item_name)
        logger.info(f"从{'文件夹' if item_type == 'directory' else '文件'}名提取标题: {item_name} -> {title}")

        search_results = movie_manager.search_tmdb(title)
        
        if search_results:
            # 使用第一个搜索结果
            first_result = search_results[0]

            # 根据分类配置匹配分类
            category_name = movie_manager.match_category(first_result)
            logger.info(f"TMDB匹配成功: {title} -> 分类: {category_name}")

            # 检查分类文件夹是否存在，不存在则创建
            category_folder = movie_manager.create_category_folder(base_path, category_name)

            if category_folder:
                # 直接移动原始文件或文件夹到分类文件夹
                if item_type == 'directory':
                    new_path = movie_manager.move_directory_to_category(item_path, category_folder)
                else:
                    new_path = movie_manager.move_file_to_category(item_path, category_folder)

                if new_path:
                    # 记录文件路径映射
                    movie_manager.processed_files[item_name] = {
                        'original_path': item_path,
                        'new_path': new_path,
                        'category': category_name,
                        'tmdb_info': first_result,
                        'type': item_type
                    }

                    results.append({
                        'filename': item_name,
                        'category': category_name,
                        'new_path': new_path,
                        'status': 'success',
                        'type': item_type
                    })
                    success_count += 1
                    logger.info(f"{'文件夹' if item_type == 'directory' else '文件'}处理成功: {item_name} -> {category_name}/")
                else:
                    results.append({
                        'filename': item_name,
                        'status': 'error',
                        'message': f"移动{'文件夹' if item_type == 'directory' else '文件'}失败",
                        'type': item_type
                    })
                    error_count += 1
                    logger.error(f"{'文件夹' if item_type == 'directory' else '文件'}移动失败: {item_name}")
            else:
                results.append({
                    'filename': item_name,
                    'status': 'error',
                    'message': '创建分类文件夹失败',
                    'type': item_type
                })
                error_count += 1
                logger.error(f"创建分类文件夹失败: {item_name} -> {category_name}")
        else:
            results.append({
                'filename': item_name,
                'status': 'error',
                'message': '未找到匹配的影视作品',
                'type': item_type
            })
            error_count += 1
            logger.warning(f"未找到TMDB匹配: {item_name} -> {title}")

    logger.info(f"文件分类处理完成 - 成功: {success_count}, 失败: {error_count}")

    # 保存处理结果数据
    if success_count > 0:
        movie_manager.save_data()
        logger.info("文件处理数据已保存")

    return jsonify({'results': results})

@app.route('/api/scan_torrents', methods=['POST'])
def api_scan_torrents():
    """扫描种子文件API"""
    data = request.get_json()
    torrent_path = data.get('torrent_path', '')

    logger.info(f"API请求 - 扫描种子文件: {torrent_path}")

    if not torrent_path:
        logger.warning("扫描种子文件API - 路径参数为空")
        return jsonify({'error': '种子文件夹路径不能为空'}), 400

    torrent_files = movie_manager.scan_torrent_files(torrent_path)
    logger.info(f"扫描种子文件完成 - 找到 {len(torrent_files)} 个种子文件")
    return jsonify({'torrent_files': torrent_files})

@app.route('/api/match_torrents', methods=['POST'])
def api_match_torrents():
    """匹配种子文件API"""
    data = request.get_json()
    torrent_path = data.get('torrent_path', '')

    logger.info(f"API请求 - 匹配种子文件: {torrent_path}")

    if not torrent_path:
        logger.warning("匹配种子文件API - 路径参数为空")
        return jsonify({'error': '种子文件夹路径不能为空'}), 400

    # 扫描种子文件
    torrent_files = movie_manager.scan_torrent_files(torrent_path)
    logger.info(f"扫描到 {len(torrent_files)} 个种子文件")

    # 匹配种子文件
    match_result = movie_manager.match_torrents_with_files(torrent_files)
    logger.info(f"种子匹配完成 - 匹配成功: {len(match_result['matched'])}, 未匹配: {len(match_result['unmatched'])}")

    return jsonify(match_result)

@app.route('/api/remove_torrent', methods=['POST'])
def api_remove_torrent():
    """移除种子并记录API"""
    data = request.get_json()

    torrent_info = data.get('torrent_info', {})
    matched_info = data.get('matched_info', {})

    logger.info(f"API请求 - 移除种子: {torrent_info.get('name', '')}")

    if not torrent_info or not matched_info:
        logger.warning("移除种子API - 参数不完整")
        return jsonify({'error': '参数不完整'}), 400

    try:
        # 记录移除的种子
        movie_manager.add_removed_torrent_record(torrent_info, matched_info)

        logger.info(f"种子移除记录成功: {torrent_info.get('name', '')}")
        return jsonify({'status': 'success', 'message': '种子已移除并记录'})

    except Exception as e:
        logger.error(f"移除种子记录失败: {e}")
        return jsonify({'status': 'error', 'message': f'移除失败: {str(e)}'}), 500

@app.route('/api/config_qb', methods=['POST'])
def api_config_qb():
    """配置qBittorrent API"""
    data = request.get_json()

    qb_host = data.get('qb_host', '').rstrip('/')
    qb_username = data.get('qb_username', '')

    logger.info(f"API请求 - 配置qBittorrent: {qb_host}, 用户: {qb_username}")

    movie_manager.qb_host = qb_host
    movie_manager.qb_username = qb_username
    movie_manager.qb_password = data.get('qb_password', '')

    # 测试连接
    if movie_manager.qb_login():
        # 保存配置
        movie_manager.save_config()
        logger.info("qBittorrent配置成功并已保存")
        return jsonify({'status': 'success', 'message': 'qBittorrent配置成功'})
    else:
        logger.error("qBittorrent配置失败 - 连接测试失败")
        return jsonify({'status': 'error', 'message': 'qBittorrent连接失败'}), 400

@app.route('/api/config_tmdb', methods=['POST'])
def api_config_tmdb():
    """配置TMDB API"""
    data = request.get_json()

    api_key = data.get('tmdb_api_key', '')
    logger.info(f"API请求 - 配置TMDB API密钥: {'*' * (len(api_key) - 4) + api_key[-4:] if len(api_key) > 4 else '****'}")

    movie_manager.tmdb_api_key = api_key

    # 测试API密钥
    test_results = movie_manager.search_tmdb('test')
    if test_results is not None:
        # 保存配置
        movie_manager.save_config()
        logger.info("TMDB API配置成功并已保存")
        return jsonify({'status': 'success', 'message': 'TMDB API配置成功'})
    else:
        logger.error("TMDB API配置失败 - 密钥无效")
        return jsonify({'status': 'error', 'message': 'TMDB API密钥无效'}), 400

@app.route('/api/config', methods=['GET', 'POST'])
def handle_config():
    """处理所有配置信息"""
    if request.method == 'GET':
        # 返回所有配置信息
        config_data = {
            'tmdb_api_key': movie_manager.tmdb_api_key or '',
            'qb_host': movie_manager.qb_host or '',
            'qb_username': movie_manager.qb_username or '',
            'qb_password': movie_manager.qb_password or '',
            'movie_path': movie_manager.movie_path or '',
            'exclude_dirs': movie_manager.exclude_dirs or [],
            'torrent_path': movie_manager.torrent_path or '',
            'skip_verify': movie_manager.skip_verify,
            'auto_start': movie_manager.auto_start,
            'monitor_interval': movie_manager.monitor_interval,
            'enable_monitoring': movie_manager.enable_monitoring
        }
        return jsonify({
            'status': 'success',
            'config': config_data
        })

    elif request.method == 'POST':
        data = request.json

        # 更新配置
        if 'tmdb_api_key' in data:
            movie_manager.tmdb_api_key = data['tmdb_api_key']
        if 'qb_host' in data:
            movie_manager.qb_host = data['qb_host']
        if 'qb_username' in data:
            movie_manager.qb_username = data['qb_username']
        if 'qb_password' in data:
            movie_manager.qb_password = data['qb_password']
        if 'movie_path' in data:
            movie_manager.movie_path = data['movie_path']
        if 'exclude_dirs' in data:
            movie_manager.exclude_dirs = data['exclude_dirs']
        if 'torrent_path' in data:
            movie_manager.torrent_path = data['torrent_path']
        if 'skip_verify' in data:
            movie_manager.skip_verify = data['skip_verify']
        if 'auto_start' in data:
            movie_manager.auto_start = data['auto_start']
        if 'monitor_interval' in data:
            movie_manager.monitor_interval = max(10, int(data['monitor_interval']))  # 最小10秒
        if 'enable_monitoring' in data:
            old_monitoring = movie_manager.enable_monitoring
            movie_manager.enable_monitoring = data['enable_monitoring']

            # 处理监控状态变化
            if movie_manager.enable_monitoring and not old_monitoring:
                movie_manager.start_monitoring()
            elif not movie_manager.enable_monitoring and old_monitoring:
                movie_manager.stop_monitoring()

        movie_manager.save_config()
        return jsonify({'status': 'success', 'message': '配置保存成功'})

@app.route('/api/category-config', methods=['GET', 'POST'])
def handle_category_config():
    """处理分类配置"""
    if request.method == 'GET':
        config_text = movie_manager.get_category_config_text()
        return jsonify({
            'status': 'success',
            'config_text': config_text
        })

    elif request.method == 'POST':
        data = request.json
        config_text = data.get('config_text', '')

        if movie_manager.save_category_config(config_text):
            return jsonify({
                'status': 'success',
                'message': '分类配置保存成功'
            })
        else:
            return jsonify({
                'status': 'error',
                'message': '分类配置保存失败，请检查YAML格式'
            })

@app.route('/api/add_torrents', methods=['POST'])
def api_add_torrents():
    """批量添加种子到qBittorrent"""
    data = request.get_json()
    matched_torrents = data.get('matched_torrents', [])

    # 获取高级功能参数
    skip_verify = data.get('skip_verify', None)  # None表示使用全局配置
    auto_start = data.get('auto_start', None)

    logger.info(f"API请求 - 批量添加种子: {len(matched_torrents)} 个种子")
    logger.info(f"高级参数 - 跳过校验: {skip_verify}, 自动开始: {auto_start}")

    results = []
    success_count = 0
    error_count = 0

    for item in matched_torrents:
        torrent_info = item.get('torrent', {})
        matched_file = item.get('matched_file', {})

        torrent_name = torrent_info.get('name', 'Unknown')
        torrent_path = torrent_info.get('path')

        # 使用智能确定的下载路径
        download_path = matched_file.get('download_path', '')
        match_type = matched_file.get('match_type', 'unknown')

        logger.info(f"处理种子: {torrent_name} -> {download_path} (策略: {match_type})")

        if torrent_path and download_path:
            # 根据种子标题确定分类
            category = movie_manager.determine_category_for_torrent(torrent_info)

            success = movie_manager.qb_add_torrent(torrent_path, download_path, category, skip_verify, auto_start)
            if success:
                success_count += 1
                logger.info(f"种子添加成功: {torrent_name} (分类: {category})")
            else:
                error_count += 1
                logger.error(f"种子添加失败: {torrent_name}")

            results.append({
                'torrent_name': torrent_name,
                'download_path': download_path,
                'match_type': match_type,
                'status': 'success' if success else 'error'
            })
        else:
            error_count += 1
            logger.error(f"种子路径信息不完整: {torrent_name}")
            results.append({
                'torrent_name': torrent_name,
                'status': 'error',
                'message': '路径信息不完整'
            })

    logger.info(f"批量添加种子完成 - 成功: {success_count}, 失败: {error_count}")
    return jsonify({'results': results})

@app.route('/api/get_processed_files')
def api_get_processed_files():
    """获取已处理的文件列表"""
    return jsonify({'processed_files': movie_manager.processed_files})

@app.route('/api/get_config_status')
def api_get_config_status():
    """获取配置状态"""
    status = {
        'tmdb_configured': bool(movie_manager.tmdb_api_key),
        'qb_configured': bool(movie_manager.qb_host and movie_manager.qb_username),
        'processed_files_count': len(movie_manager.processed_files),
        'config_file_exists': os.path.exists(movie_manager.config_file),
        'data_file_exists': os.path.exists(movie_manager.data_file)
    }

    logger.info(f"配置状态查询: TMDB={'已配置' if status['tmdb_configured'] else '未配置'}, "
                f"qB={'已配置' if status['qb_configured'] else '未配置'}, "
                f"已处理文件={status['processed_files_count']}")

    return jsonify(status)

@app.route('/api/torrent_status')
def api_get_torrent_status():
    """获取种子状态信息"""
    try:
        # 获取待处理种子信息
        pending_info = []
        for tag, info in movie_manager.pending_torrents.items():
            torrent = movie_manager.qb_get_torrent_by_tag(tag)
            pending_info.append({
                'tag': tag,
                'path': info['path'],
                'download_path': info['download_path'],
                'add_time': info['add_time'].isoformat(),
                'skip_verify': info['skip_verify'],
                'auto_start': info['auto_start'],
                'torrent_info': {
                    'state': torrent.get('state', 'unknown') if torrent else 'not_found',
                    'progress': torrent.get('progress', 0) if torrent else 0,
                    'name': torrent.get('name', '') if torrent else ''
                } if torrent else None
            })

        # 获取监控状态
        monitoring_status = {
            'enabled': movie_manager.enable_monitoring,
            'running': movie_manager.monitoring_thread and movie_manager.monitoring_thread.is_alive(),
            'interval': movie_manager.monitor_interval,
            'pending_count': len(movie_manager.pending_torrents)
        }

        return jsonify({
            'status': 'success',
            'monitoring': monitoring_status,
            'pending_torrents': pending_info
        })

    except Exception as e:
        logger.error(f"获取种子状态失败: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/monitoring_control', methods=['POST'])
def api_monitoring_control():
    """控制状态监控"""
    try:
        data = request.get_json()
        action = data.get('action')

        if action == 'start':
            if not movie_manager.enable_monitoring:
                return jsonify({'status': 'error', 'message': '监控功能未启用'}), 400
            movie_manager.start_monitoring()
            return jsonify({'status': 'success', 'message': '监控已启动'})

        elif action == 'stop':
            movie_manager.stop_monitoring()
            return jsonify({'status': 'success', 'message': '监控已停止'})

        elif action == 'check_now':
            movie_manager._check_pending_torrents()
            return jsonify({'status': 'success', 'message': '立即检查完成'})

        else:
            return jsonify({'status': 'error', 'message': '无效的操作'}), 400

    except Exception as e:
        logger.error(f"控制监控失败: {e}")
        return jsonify({'status': 'error', 'message': str(e)}), 500

@app.route('/api/reset_data', methods=['POST'])
def api_reset_data():
    """重置数据（清空已处理文件记录）"""
    try:
        movie_manager.processed_files = {}
        movie_manager.save_data()
        logger.info("数据已重置，已处理文件记录已清空")
        return jsonify({'status': 'success', 'message': '数据重置成功'})
    except Exception as e:
        logger.error(f"数据重置失败: {e}")
        return jsonify({'status': 'error', 'message': f'数据重置失败: {e}'}), 500

@app.route('/api/debug_scan', methods=['POST'])
def api_debug_scan():
    """调试扫描结果"""
    data = request.get_json()
    path = data.get('path', '')
    exclude_dirs = data.get('exclude_dirs', [])

    logger.info(f"调试扫描 - 路径: {path}, 排除: {exclude_dirs}")

    if not path:
        return jsonify({'error': '路径不能为空'}), 400

    result = movie_manager.scan_directory(path, exclude_dirs)

    # 详细日志记录
    logger.info(f"调试扫描结果:")
    logger.info(f"  - 总文件数: {result['total_files']}")
    logger.info(f"  - 总目录数: {result['total_dirs']}")
    logger.info(f"  - 文件列表长度: {len(result['files'])}")
    logger.info(f"  - 目录列表长度: {len(result['directories'])}")

    # 打印前几个文件和目录的详细信息
    if result['files']:
        logger.info("前3个文件:")
        for i, file in enumerate(result['files'][:3]):
            logger.info(f"  文件{i+1}: {file}")

    if result['directories']:
        logger.info("前3个目录:")
        for i, dir in enumerate(result['directories'][:3]):
            logger.info(f"  目录{i+1}: {dir}")

    return jsonify(result)

if __name__ == '__main__':
    logger.info("=" * 50)
    logger.info("影视文件管理系统启动")
    logger.info("=" * 50)
    logger.info("系统功能:")
    logger.info("1. 扫描影视文件路径")
    logger.info("2. TMDB API搜索影视类目")
    logger.info("3. 自动分类和移动文件")
    logger.info("4. 匹配种子文件")
    logger.info("5. qBittorrent自动下载")
    logger.info("6. 智能校验控制和状态监控")
    logger.info("=" * 50)
    logger.info("Web界面地址: http://localhost:5000")
    logger.info("=" * 50)

    # 启动时自动开启监控（如果配置启用）
    if movie_manager.enable_monitoring:
        movie_manager.start_monitoring()
        logger.info("状态监控已自动启动")

    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        logger.info("用户中断，系统正在关闭...")
    except Exception as e:
        logger.error(f"系统启动失败: {e}")
    finally:
        # 关闭监控线程
        movie_manager.stop_monitoring()
        logger.info("影视文件管理系统已关闭")
