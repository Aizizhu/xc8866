# xc8866
从xc8866网站爬取公开交友信息整合成表格和简易查询网页
https://xc8866.com/


环境要求:
python3.10.x

需要使用venv

命令：python -m venv venv

call venv\Scripts\activate

pip install -r requirements.txt


代理要求：

在start.bat内有

set http_proxy=http://127.0.0.1:7890

set https_proxy=http://127.0.0.1:7890

set no_proxy=localhost,127.0.0.1,::1

修改成自己的端口


用法：

使用start.bat开始，运行后粘贴需要开始的页面链接输入需要结束的页面数，会利用下一页按钮自动进入下一页直到设置的页面数为止。

![21](https://github.com/user-attachments/assets/7ae5e10c-cb51-4bf6-a79f-93578953b150)


中途可以ctrl+c停止，停止前会写入以爬取的内容到output.xlsx,同时会生成一个crawled_posts.txt，里面记录了已经爬取过的页面用来实现跳过重复页面和断点续传。
![22](https://github.com/user-attachments/assets/edd80c2a-dc82-40dc-a569-7764b7928c04)


爬取完成后运行db.bat将output内容导入库
![23](https://github.com/user-attachments/assets/900e5c94-3f49-44d2-bc8f-93392500b5a9)


导入完成后运行web.bat就可以查询了。
![26](https://github.com/user-attachments/assets/dbf1f585-4260-4577-b177-20e485ed7c5f)
![25](https://github.com/user-attachments/assets/4bb5bc8f-c344-4769-865a-b519017d0532)
