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
from difflib import SequenceMatcher

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

                logger.info(f"配置文件加载成功: {self.config_file}")
                logger.info(f"TMDB API: {'已配置' if self.tmdb_api_key else '未配置'}")
                logger.info(f"qBittorrent: {'已配置' if self.qb_host else '未配置'}")
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

                logger.info(f"数据文件加载成功: {self.data_file}")
                logger.info(f"已处理文件数量: {len(self.processed_files)}")
            else:
                logger.info("数据文件不存在，将创建新的数据文件")
        except Exception as e:
            logger.error(f"加载数据文件失败: {e}")
            self.processed_files = {}

    def save_data(self):
        """保存数据文件"""
        try:
            data = {
                'processed_files': self.processed_files,
                'last_updated': time.time(),
                'total_processed': len(self.processed_files)
            }

            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

            logger.info(f"数据文件保存成功: {self.data_file}, 已处理文件: {len(self.processed_files)}")
        except Exception as e:
            logger.error(f"保存数据文件失败: {e}")

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
        """从种子文件名中提取影视作品标题（特殊处理）"""
        # 移除文件扩展名
        name = os.path.splitext(filename)[0]
        original_name = name

        logger.debug(f"开始提取种子标题: {filename}")

        # 种子文件特殊预处理：去除第一个中括号及其后面的点
        # 1. 去除第一个中括号及其内容，以及紧跟着的点
        bracket_match = re.search(r'^\[([^\]]+)\]\.?', name)
        if bracket_match:
            # 移除第一个中括号及其内容，以及可能紧跟的点
            name = name[bracket_match.end():].strip()
            logger.debug(f"移除第一个中括号及后面的点后: {name}")

        # 如果处理后的名称为空或太短，使用原始文件名
        if len(name.strip()) < 2:
            logger.warning(f"种子预处理后标题太短，使用原始文件名: {original_name}")
            name = original_name

        # 2. 使用标准的标题提取规则处理剩余内容
        extracted_title = self.extract_title_from_filename(name + ".dummy")  # 添加假扩展名避免影响处理

        logger.info(f"种子标题提取完成: '{filename}' -> '{extracted_title}'")
        return extracted_title

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

    def match_torrents_with_files(self, torrent_files: List[Dict]) -> Dict:
        """匹配种子文件与已处理的影视文件"""
        matched = []
        unmatched = []

        logger.info(f"开始匹配种子文件: {len(torrent_files)} 个种子, {len(self.processed_files)} 个已处理文件")

        for torrent in torrent_files:
            torrent_title = torrent['title'].lower()
            torrent_name = torrent['name']
            best_match = None
            best_score = 0
            best_filename = ""

            logger.debug(f"匹配种子: {torrent_name} -> 提取标题: {torrent['title']}")

            # 与已处理的文件进行匹配
            for filename, file_info in self.processed_files.items():
                # 提取文件标题进行比较
                file_title = self.extract_title_from_filename(filename).lower()

                # 计算相似度
                similarity = SequenceMatcher(None, torrent_title, file_title).ratio()

                if similarity > best_score and similarity > 0.6:  # 相似度阈值
                    best_score = similarity
                    best_match = file_info
                    best_filename = filename

            if best_match:
                logger.info(f"种子匹配成功: {torrent_name} -> {best_filename} (相似度: {best_score:.2f})")
                matched.append({
                    'torrent': torrent,
                    'matched_file': best_match,
                    'similarity': best_score
                })
            else:
                logger.warning(f"种子未找到匹配: {torrent_name} -> {torrent['title']}")
                unmatched.append(torrent)

        logger.info(f"种子匹配完成 - 匹配成功: {len(matched)}, 未匹配: {len(unmatched)}")
        return {
            'matched': matched,
            'unmatched': unmatched
        }

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
                return True
            else:
                logger.error("qBittorrent登录失败")
                return False

        except Exception as e:
            logger.error(f"qBittorrent登录异常: {e}")
            return False

    def qb_add_torrent(self, torrent_path: str, download_path: str) -> bool:
        """添加种子到qBittorrent"""
        try:
            if not hasattr(self, 'qb_cookies'):
                if not self.qb_login():
                    return False

            add_url = f"{self.qb_host}/api/v2/torrents/add"

            with open(torrent_path, 'rb') as f:
                files = {'torrents': f}
                data = {
                    'savepath': download_path,
                    'category': 'movie_manager',
                    'tags': 'auto_added'
                }

                response = requests.post(
                    add_url,
                    files=files,
                    data=data,
                    cookies=self.qb_cookies,
                    timeout=30
                )
                response.raise_for_status()

                if response.text == "Ok.":
                    logger.info(f"成功添加种子: {torrent_path}")
                    return True
                else:
                    logger.error(f"添加种子失败: {response.text}")
                    return False

        except Exception as e:
            logger.error(f"添加种子异常: {e}")
            return False

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
            'torrent_path': movie_manager.torrent_path or ''
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

    logger.info(f"API请求 - 批量添加种子: {len(matched_torrents)} 个种子")

    results = []
    success_count = 0
    error_count = 0

    for item in matched_torrents:
        torrent_info = item.get('torrent', {})
        matched_file = item.get('matched_file', {})

        torrent_name = torrent_info.get('name', 'Unknown')
        torrent_path = torrent_info.get('path')
        download_path = os.path.dirname(matched_file.get('new_path', ''))

        logger.info(f"处理种子: {torrent_name} -> {download_path}")

        if torrent_path and download_path:
            success = movie_manager.qb_add_torrent(torrent_path, download_path)
            if success:
                success_count += 1
                logger.info(f"种子添加成功: {torrent_name}")
            else:
                error_count += 1
                logger.error(f"种子添加失败: {torrent_name}")

            results.append({
                'torrent_name': torrent_name,
                'download_path': download_path,
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
    logger.info("=" * 50)
    logger.info("Web界面地址: http://localhost:5000")
    logger.info("=" * 50)

    try:
        app.run(debug=True, host='0.0.0.0', port=5000)
    except KeyboardInterrupt:
        logger.info("用户中断，系统正在关闭...")
    except Exception as e:
        logger.error(f"系统启动失败: {e}")
    finally:
        logger.info("影视文件管理系统已关闭")
