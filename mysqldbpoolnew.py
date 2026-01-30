#文件名: /root/policy/mysqldbpoolnew.py
import pymysql
from dbutils.pooled_db import PooledDB
import datetime
from decimal import Decimal
import logging
import time
import sys
from typing import List, Union, Dict, Any, Optional, Tuple

# 配置日志记录
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


mysql_host = "rm-bp193qq9h865dwnta5o.mysql.rds.aliyuncs.com"
mysql_port = 3629
mysql_user = "city_walk"
mysql_password = "qEqMKAtqBgmOLc2KK9F9"
mysql_database = "city_walk"



# 创建数据库连接池
pool = PooledDB(
    creator=pymysql,
    maxconnections=10,
    mincached=2,
    maxcached=5,
    maxshared=0,
    blocking=True,
    maxusage=None,
    setsession=[],
    ping=30,
    host=mysql_host,
    port=mysql_port,
    user=mysql_user,
    password=mysql_password,
    database=mysql_database,
    charset='utf8mb4',
    autocommit=True,
)

MAX_RETRIES = 3
RETRY_DELAY = 1  # 重试间隔时间（秒）

def get_connection():
    """获取数据库连接"""
    retries = 0
    while retries < MAX_RETRIES:
        try:
            conn = pool.connection()
            logger.info(f"从连接池获取到连接，当前空闲连接数: {len(pool._idle_cache)}")
            return conn
        except Exception as e:
            retries += 1
            if retries < MAX_RETRIES:
                logger.warning(f"获取数据库连接失败，第 {retries} 次重试，错误信息: {e}")
                time.sleep(RETRY_DELAY)
            else:
                logger.error(f"获取数据库连接失败，达到最大重试次数，错误信息: {e}")
                raise

def format_jsonobj_values_by_type(jsonobj):
    for key, value in jsonobj.items():
        if isinstance(value, datetime.datetime):
            jsonobj[key] = value.strftime('%Y-%m-%d %H:%M:%S')
        elif isinstance(value, Decimal):
            jsonobj[key] = float(value)
    return jsonobj

# 定义一个依赖来获取数据库连接
def get_db_connection():
    db = get_connection()
    try:
        yield db
    finally:
        db.close()
        logger.info(f"连接已归还到连接池，当前空闲连接数: {len(pool._idle_cache)}")

def close_pool():
    if pool:
        try:
            pool.close()
            logger.info("数据库连接池已关闭")
        except Exception as e:
            logger.error(f"关闭数据库连接池时出错: {e}")
            
def get_error_details():
    exc_info = sys.exc_info()
    error_traceback = exc_info[2]
    error_details = f'模块发生错误\n'
    while error_traceback.tb_next is not None:
        error_frame = error_traceback.tb_frame
        error_details += f"追溯错误到{error_frame.f_code.co_filename} 第{error_traceback.tb_lineno}行\n"
        error_traceback = error_traceback.tb_next
    error_frame = error_traceback.tb_frame
    error_details += f"错误最终发生于{error_frame.f_code.co_filename}\n"
    error_details += f"第{error_traceback.tb_lineno}行\n"
    if len(error_details+f"错误信息：{str(exc_info[1].args)}\n") > 500:
        error_details += f"错误信息：{str(exc_info[1].args)[:250]}......{str(exc_info[1].args)[-250:]}\n"
    else:
        error_details += f"错误信息：{exc_info[1].args}\n"
    error_details += "局部变量:\n"
    param_str = ''
    for param in error_frame.f_locals:
        if len(param_str) < 200:
            param_str += (f"{param}={error_frame.f_locals[param]}\n")
        else:
            break
    error_details += param_str
    return error_details            


class DynamicQueryBuilder:
    def __init__(self, base_query: str):
        self.query = base_query
        self.params = []
        self.has_where = "WHERE" in base_query.upper()
    
    def add_conditions(self, conditions: Union[Dict, Any], allowed_fields: Optional[List[str]] = None) -> 'DynamicQueryBuilder':
        """
        添加动态条件
        
        Args:
            conditions: 条件字典或Pydantic模型
            allowed_fields: 允许查询的字段白名单
        """
        # 统一转换为字典
        if hasattr(conditions, 'model_dump'):
            conditions_dict = conditions.model_dump()  # Pydantic v2
        elif hasattr(conditions, 'dict'):
            conditions_dict = conditions.dict()        # Pydantic v1
        else:
            conditions_dict = conditions
        
        if allowed_fields is None:
            allowed_fields = conditions_dict.keys()
        
        for field, value in conditions_dict.items():
            if field in allowed_fields and value is not None:
                self._add_condition(field, value)
        
        return self
    
    def _add_condition(self, field: str, value: Any) -> None:
        """添加单个条件"""
        # 确保有WHERE子句
        if not self.has_where:
            self.query += " WHERE 1=1"
            self.has_where = True
        
        # 处理字典形式（带操作符）
        if isinstance(value, dict) and 'operator' in value:
            operator = value['operator']
            actual_value = value['value']
            
            if operator == 'like':
                self.query += f" AND {field} LIKE %s"
                self.params.append(f"%{actual_value}%")
            elif operator == 'in':
                if isinstance(actual_value, list) and actual_value:
                    placeholders = ', '.join(['%s'] * len(actual_value))
                    self.query += f" AND {field} IN ({placeholders})"
                    self.params.extend(actual_value)
            elif operator in ('>', '<', '>=', '<=', '!='):
                self.query += f" AND {field} {operator} %s"
                self.params.append(actual_value)
        
        # 处理列表类型（自动IN操作）
        elif isinstance(value, list):
            if value:
                placeholders = ', '.join(['%s'] * len(value))
                self.query += f" AND {field} IN ({placeholders})"
                self.params.extend(value)
        
        # 处理字符串类型（智能LIKE判断）
        elif isinstance(value, str):
            if '%' in value:
                self.query += f" AND {field} LIKE %s"
                self.params.append(value)
            else:
                self.query += f" AND {field} = %s"
                self.params.append(value)
        
        # 处理其他类型（默认等于操作）
        else:
            self.query += f" AND {field} = %s"
            self.params.append(value)
    
    def add_custom_condition(self, condition: str, params: Optional[List] = None) -> 'DynamicQueryBuilder':
        """添加自定义条件"""
        if not self.has_where:
            self.query += " WHERE 1=1"
            self.has_where = True
        
        self.query += f" AND {condition}"
        if params:
            self.params.extend(params)
        
        return self
    
    def group_by(self, fields: Union[str, List[str]]) -> 'DynamicQueryBuilder':
        """添加GROUP BY子句"""
        if isinstance(fields, list):
            self.query += f" GROUP BY {', '.join(fields)}"
        else:
            self.query += f" GROUP BY {fields}"
        return self
    
    def order_by(self, fields: Union[str, List[str]], direction: str = "ASC") -> 'DynamicQueryBuilder':
        """添加ORDER BY子句"""
        if isinstance(fields, list):
            order_clause = ', '.join([f"{field} {direction}" for field in fields])
            self.query += f" ORDER BY {order_clause}"
        else:
            self.query += f" ORDER BY {fields} {direction}"
        return self
    
    def limit(self, count: int) -> 'DynamicQueryBuilder':
        """添加LIMIT子句"""
        self.query += f" LIMIT {count}"
        return self
    
    def offset(self, count: int) -> 'DynamicQueryBuilder':
        """添加OFFSET子句"""
        self.query += f" OFFSET {count}"
        return self
    
    def build(self) -> Tuple[str, tuple]:
        """构建最终的查询和参数"""
        return self.query, tuple(self.params)
    
    def execute(self, cursor) -> List[Dict]:
        """修复版的execute方法"""
        try:
            cursor.execute(self.query, self.params)
            raw_results = cursor.fetchall()
            
            # 检查游标类型 - 可能已经是字典游标
            if hasattr(cursor, 'description'):
                columns = [desc[0] for desc in cursor.description]
            else:
                columns = []
            
            # 处理不同类型的结果
            formatted_results = []
            for item in raw_results:
                if isinstance(item, dict):
                    # 已经是字典，直接使用
                    formatted_results.append(item.copy())  # 创建副本避免引用问题
                elif isinstance(item, (tuple, list)):
                    # 是元组或列表，需要转换
                    row_dict = {}
                    for i, value in enumerate(item):
                        col_name = columns[i] if i < len(columns) else f'col_{i}'
                        row_dict[col_name] = value
                    formatted_results.append(row_dict)
                else:
                    # 其他类型，直接包装
                    formatted_results.append({'result': item})
            
            return formatted_results
            
        except Exception as e:
            print(f"详细错误信息: {repr(e)}")
            import traceback
            traceback.print_exc()  # 打印完整的堆栈跟踪
            raise