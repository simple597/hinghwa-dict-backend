# Generated by Django 3.1.14 on 2023-11-16 08:38

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('rewards', '0001_initial'),
    ]

    operations = [
        migrations.AlterModelOptions(
            name='order',
            options={'verbose_name': '订单', 'verbose_name_plural': '订单'},
        ),
        migrations.AlterModelOptions(
            name='product',
            options={'verbose_name': '商品', 'verbose_name_plural': '商品'},
        ),
        migrations.AlterModelOptions(
            name='title',
            options={'verbose_name': '头衔', 'verbose_name_plural': '头衔'},
        ),
        migrations.AlterModelOptions(
            name='transaction',
            options={'verbose_name': '积分记录', 'verbose_name_plural': '积分记录'},
        ),
    ]
