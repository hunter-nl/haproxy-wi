import json

from flask import render_template

import modules.db.sql as sql
import modules.config.config as config_mod
import modules.server.server as server_mod
import modules.roxywi.common as roxywi_common
import modules.roxy_wi_tools as roxy_wi_tools

time_zone = sql.get_setting('time_zone')
get_date = roxy_wi_tools.GetDate(time_zone)
get_config_var = roxy_wi_tools.GetConfigVar()


def show_frontend_backend(serv: str, backend: str) -> str:
	haproxy_sock_port = int(sql.get_setting('haproxy_sock_port'))
	cmd = 'echo "show servers state"|nc %s %s |grep "%s" |awk \'{print $4}\'' % (serv, haproxy_sock_port, backend)
	output, stderr = server_mod.subprocess_execute(cmd)
	lines = ''
	for i in output:
		if i == ' ':
			continue
		i = i.strip()
		lines += i + '<br>'
	return lines


def show_server(serv: str, backend: str, backend_server: str) -> str:
	haproxy_sock_port = int(sql.get_setting('haproxy_sock_port'))
	cmd = 'echo "show servers state"|nc %s %s |grep "%s" |grep "%s" |awk \'{print $5":"$19}\' |head -1' % (
		serv, haproxy_sock_port, backend, backend_server)
	output, stderr = server_mod.subprocess_execute(cmd)
	return output[0]


def get_all_stick_table(serv: str):
	hap_sock_p = sql.get_setting('haproxy_sock_port')
	cmd = 'echo "show table"|nc %s %s |awk \'{print $3}\' | tr -d \'\n\' | tr -d \'[:space:]\'' % (serv, hap_sock_p)
	output, stderr = server_mod.subprocess_execute(cmd)
	return output[0]


def get_stick_table(serv: str, table: str):
	hap_sock_p = sql.get_setting('haproxy_sock_port')
	cmd = 'echo "show table %s"|nc %s %s |awk -F"#" \'{print $2}\' |head -1 | tr -d \'\n\'' % (table, serv, hap_sock_p)
	output, stderr = server_mod.subprocess_execute(cmd)
	tables_head = []
	for i in output[0].split(','):
		i = i.split(':')[1]
		tables_head.append(i)

	cmd = 'echo "show table %s"|nc %s %s |grep -v "#"' % (table, serv, hap_sock_p)
	output, stderr = server_mod.subprocess_execute(cmd)

	return tables_head, output


def show_backends(server_ip, **kwargs):
	hap_sock_p = sql.get_setting('haproxy_sock_port')
	cmd = f'echo "show backend" |nc {server_ip} {hap_sock_p}'
	output, stderr = server_mod.subprocess_execute(cmd)
	lines = ''
	if stderr:
		roxywi_common.logging('Roxy-WI server', ' ' + stderr, roxywi=1)
	if kwargs.get('ret'):
		ret = list()
	else:
		ret = ""
	for line in output:
		if any(s in line for s in ('#', 'stats', 'MASTER', '<')):
			continue
		if len(line) > 1:
			back = json.dumps(line).split("\"")
			if kwargs.get('ret'):
				ret.append(back[1])
			else:
				lines += back[1] + "<br>"

	if kwargs.get('ret'):
		return ret

	return lines


def get_backends_from_config(server_ip: str, backends='') -> str:
	config_date = get_date.return_date('config')
	configs_dir = get_config_var.get_config_var('configs', 'haproxy_save_configs_dir')
	format_cfg = 'cfg'
	lines = ''

	try:
		cfg = configs_dir + roxywi_common.get_files(configs_dir, format_cfg)[0]
	except Exception as e:
		roxywi_common.logging('Roxy-WI server', str(e), roxywi=1)
		try:
			cfg = f'{configs_dir}{server_ip}-{config_date}.{format_cfg}'
		except Exception as e:
			roxywi_common.logging('Roxy-WI server', f'error: Cannot generate cfg path: {e}', roxywi=1)
			return f'error: Cannot generate cfg path: {e}'
		try:
			config_mod.get_config(server_ip, cfg)
		except Exception as e:
			roxywi_common.logging('Roxy-WI server', f'error: Cannot download config: {e}', roxywi=1)
			return f'error: Cannot download config: {e}'

	with open(cfg, 'r') as f:
		for line in f:
			if backends == 'frontend':
				if (line.startswith('listen') or line.startswith('frontend')) and 'stats' not in line:
					line = line.strip()
					lines += line.split(' ')[1] + '<br>'

	return lines


def change_ip_and_port(serv, backend_backend, backend_server, backend_ip, backend_port) -> str:
	if backend_ip is None:
		return 'error: Backend IP must be IP and not 0'

	if backend_port is None:
		return 'error: The backend port must be integer and not 0'

	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	lines = ''

	masters = sql.is_master(serv)
	for master in masters:
		if master[0] is not None:
			cmd = 'echo "set server %s/%s addr %s port %s check-port %s" |nc %s %s' % (
				backend_backend, backend_server, backend_ip, backend_port, backend_port, master[0], haproxy_sock_port)
			output, stderr = server_mod.subprocess_execute(cmd)
			lines += output[0]
			roxywi_common.logging(
				master[0], 'IP address and port have been changed. On: {}/{} to {}:{}'.format(
					backend_backend, backend_server, backend_ip, backend_port
				),
				login=1, keep_history=1, service='haproxy'
			)

	cmd = 'echo "set server %s/%s addr %s port %s check-port %s" |nc %s %s' % (
		backend_backend, backend_server, backend_ip, backend_port, backend_port, serv, haproxy_sock_port)
	roxywi_common.logging(
		serv,
		f'IP address and port have been changed. On: {backend_backend}/{backend_server} to {backend_ip}:{backend_port}',
		login=1, keep_history=1, service='haproxy'
	)
	output, stderr = server_mod.subprocess_execute(cmd)

	if stderr != '':
		lines += 'error: ' + stderr[0]
	else:
		lines += output[0]
		configs_dir = get_config_var.get_config_var('configs', 'haproxy_save_configs_dir')
		cfg = f"{configs_dir}{serv}-{get_date.return_date('config')}.cfg"

		config_mod.get_config(serv, cfg)
		cmd = 'string=`grep %s %s -n -A25 |grep "server %s" |head -1|awk -F"-" \'{print $1}\'` ' \
			  '&& sed -Ei "$( echo $string)s/((1?[0-9][0-9]?|2[0-4][0-9]|25[0-5])\.){3}(1?[0-9][0-9]?|2[0-4][0-9]|25[0-5]):[0-9]+/%s:%s/g" %s' % \
			  (backend_backend, cfg, backend_server, backend_ip, backend_port, cfg)
		server_mod.subprocess_execute(cmd)
		config_mod.master_slave_upload_and_restart(serv, cfg, 'save', 'haproxy')

	return lines


def change_maxconn_global(serv: str, maxconn: int) -> str:
	if maxconn is None:
		return 'error: Maxconn must be integer and not 0'

	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	masters = sql.is_master(serv)

	for master in masters:
		if master[0] is not None:
			cmd = f'echo "set maxconn global {maxconn}" |nc {master[0]} {haproxy_sock_port}'
			output, stderr = server_mod.subprocess_execute(cmd)
		roxywi_common.logging(master[0], f'Maxconn has been changed. Globally to {maxconn}', login=1, keep_history=1, service='haproxy')

	cmd = f'echo "set maxconn global {maxconn}" |nc {serv} {haproxy_sock_port}'
	roxywi_common.logging(serv, f'Maxconn has been changed. Globally to {maxconn}', login=1, keep_history=1, service='haproxy')
	output, stderr = server_mod.subprocess_execute(cmd)

	if stderr != '':
		return stderr[0]
	elif output[0] == '':
		configs_dir = get_config_var.get_config_var('configs', 'haproxy_save_configs_dir')
		cfg = f"{configs_dir}{serv}-{get_date.return_date('config')}.cfg"

		config_mod.get_config(serv, cfg)
		cmd = 'string=`grep global %s -n -A5 |grep maxcon -n |awk -F":" \'{print $2}\'|awk -F"-" \'{print $1}\'` ' \
			  '&& sed -Ei "$( echo $string)s/[0-9]+/%s/g" %s' % (cfg, maxconn, cfg)
		server_mod.subprocess_execute(cmd)
		config_mod.master_slave_upload_and_restart(serv, cfg, 'save', 'haproxy')
		return f'success: Maxconn globally has been set to {maxconn} '
	else:
		return f'error: {output[0]}'


def change_maxconn_frontend(serv, maxconn, frontend) -> str:
	if maxconn is None:
		return 'error: Maxconn must be integer and not 0'

	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	masters = sql.is_master(serv)

	for master in masters:
		if master[0] is not None:
			cmd = f'echo "set maxconn frontend {frontend} {maxconn}" |nc {master[0]} {haproxy_sock_port}'
			output, stderr = server_mod.subprocess_execute(cmd)
		roxywi_common.logging(master[0], f'Maxconn has been changed. On: {frontend} to {maxconn}', login=1, keep_history=1, service='haproxy')

	cmd = f'echo "set maxconn frontend {frontend} {maxconn}" |nc {serv} {haproxy_sock_port}'
	roxywi_common.logging(serv, f'Maxconn has been changed. On: {frontend} to {maxconn}', login=1, keep_history=1, service='haproxy')
	output, stderr = server_mod.subprocess_execute(cmd)

	if stderr != '':
		return stderr[0]
	elif output[0] == '':
		configs_dir = get_config_var.get_config_var('configs', 'haproxy_save_configs_dir')
		cfg = f"{configs_dir}{serv}-{get_date.return_date('config')}.cfg"

		config_mod.get_config(serv, cfg)
		cmd = 'string=`grep %s %s -n -A5 |grep maxcon -n |awk -F":" \'{print $2}\'|awk -F"-" \'{print $1}\'` ' \
			  '&& sed -Ei "$( echo $string)s/[0-9]+/%s/g" %s' % (frontend, cfg, maxconn, cfg)
		server_mod.subprocess_execute(cmd)
		config_mod.master_slave_upload_and_restart(serv, cfg, 'save', 'haproxy')
		return f'success: Maxconn for {frontend} has been set to {maxconn} '
	else:
		return f'error: {output[0]}'


def change_maxconn_backend(serv, backend, backend_server, maxconn) -> str:
	if maxconn is None:
		return 'error: Maxconn must be integer and not 0'

	haproxy_sock_port = sql.get_setting('haproxy_sock_port')

	masters = sql.is_master(serv)
	for master in masters:
		if master[0] is not None:
			cmd = f'echo "set maxconn server {backend}/{backend_server} {maxconn}" |nc {master[0]} {haproxy_sock_port}'
			output, stderr = server_mod.subprocess_execute(cmd)
		roxywi_common.logging(master[0], f'Maxconn has been changed. On: {backend}/{backend_server} to {maxconn}', login=1, keep_history=1, service='haproxy')

	cmd = f'echo "set maxconn server {backend}/{backend_server} {maxconn}" |nc {serv} {haproxy_sock_port}'
	roxywi_common.logging(serv, f'Maxconn has been changed. On: {backend} to {maxconn}', login=1, keep_history=1, service='haproxy')
	output, stderr = server_mod.subprocess_execute(cmd)

	if stderr != '':
		return stderr[0]
	elif output[0] == '':
		configs_dir = get_config_var.get_config_var('configs', 'haproxy_save_configs_dir')
		cfg = f"{configs_dir}{serv}-{get_date.return_date('config')}.cfg"

		config_mod.get_config(serv, cfg)
		cmd = 'string=`grep %s %s -n -A10 |grep maxcon -n|grep %s |awk -F":" \'{print $2}\'|awk -F"-" \'{print $1}\'` ' \
			  '&& sed -Ei "$( echo $string)s/maxconn [0-9]+/maxconn %s/g" %s' % (backend, cfg, backend_server, maxconn, cfg)
		server_mod.subprocess_execute(cmd)
		config_mod.master_slave_upload_and_restart(serv, cfg, 'save', 'haproxy')
		return f'success: Maxconn for {backend}/{backend_server} has been set to {maxconn} '
	else:
		return f'error: {output[0]}'


def table_select(serv: str, table: str):
	lang = roxywi_common.get_user_lang_for_flask()

	if table == 'All':
		tables = get_all_stick_table(serv)
		table = []
		for t in tables.split(','):
			if t != '':
				table_id = []
				tables_head1, table1 = get_stick_table(serv, t)
				table_id.append(tables_head1)
				table_id.append(table1)
				table.append(table_id)

		return render_template('ajax/stick_tables.html', table=table, lang=lang)
	else:
		tables_head, table = get_stick_table(serv, table)
		return render_template('ajax/stick_table.html', tables_head=tables_head, table=table, lang=lang)


def delete_ip_from_stick_table(serv, ip, table) -> str:
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')

	cmd = f'echo "clear table {table} key {ip}" |nc {serv} {haproxy_sock_port}'
	output, stderr = server_mod.subprocess_execute(cmd)
	try:
		if stderr[0] != '':
			return f'error: {stderr[0]}'
	except Exception:
		return 'ok'


def clear_stick_table(serv, table) -> str:
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')

	cmd = f'echo "clear table {table} " |nc {serv} {haproxy_sock_port}'
	output, stderr = server_mod.subprocess_execute(cmd)
	try:
		if stderr[0] != '':
			return f'error: {stderr[0]}'
	except Exception:
		return 'ok'


def list_of_lists(serv) -> str:
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	cmd = f'echo "show acl"|nc {serv} {haproxy_sock_port} |grep "loaded from" |awk \'{{print $1,$2}}\''
	output, stderr = server_mod.subprocess_execute(cmd)
	try:
		return output[0]
	except Exception:
		return '------'


def show_lists(serv, list_id, color, list_name) -> None:
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	cmd = f'echo "show acl #{list_id}"|nc {serv} {haproxy_sock_port}'
	output, stderr = server_mod.subprocess_execute(cmd)

	return render_template('ajax/list.html', list=output, list_id=list_id, color=color, list_name=list_name)


def delete_ip_from_list(serv, ip_id, ip, list_id, list_name) -> str:
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	lib_path = get_config_var.get_config_var('main', 'lib_path')
	user_group = roxywi_common.get_user_group(id=1)
	cmd = f"sed -i 's!{ip}$!!' {lib_path}/lists/{user_group}/{list_name}"
	cmd1 = f"sed -i '/^$/d' {lib_path}/lists/{user_group}/{list_name}"
	output, stderr = server_mod.subprocess_execute(cmd)
	output1, stderr1 = server_mod.subprocess_execute(cmd1)
	if output:
		return f'error: {output}'
	if stderr:
		return f'error: {stderr}'
	if output1:
		return f'error: {output1}'
	if stderr1:
		return f'error: {stderr}'

	cmd = f'echo "del acl #{list_id} #{ip_id}" |nc {serv} {haproxy_sock_port}'
	output, stderr = server_mod.subprocess_execute(cmd)

	roxywi_common.logging(serv, f'{ip_id} has been delete from list {list_id}', login=1, keep_history=1, service='haproxy')
	try:
		if output[0] != '':
			return f'error: {output[0]}'
	except Exception:
		pass
	try:
		if stderr != '':
			return f'error: {stderr[0]}'
	except Exception:
		pass


def add_ip_to_list(serv, ip, list_id, list_name) -> str:
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	lib_path = get_config_var.get_config_var('main', 'lib_path')
	user_group = roxywi_common.get_user_group(id=1)
	cmd = f'echo "add acl #{list_id} {ip}" |nc {serv} {haproxy_sock_port}'
	output, stderr = server_mod.subprocess_execute(cmd)
	try:
		if output[0]:
			return f'error: {output[0]}'
	except Exception:
		pass
	try:
		if stderr:
			print(f'error: {stderr[0]}')
	except Exception:
		pass

	if 'is not a valid IPv4 or IPv6 address' not in output[0]:
		cmd = f'echo "{ip}" >> {lib_path}/lists/{user_group}/{list_name}'
		print(cmd)
		output, stderr = server_mod.subprocess_execute(cmd)
		roxywi_common.logging(serv, f'{ip} has been added to list {list_id}', login=1, keep_history=1, service='haproxy')
		if output:
			return f'error: {output}'
		if stderr:
			return f'error: {stderr}'
	return 'ok'


def select_session(server_ip: str) -> str:
	lang = roxywi_common.get_user_lang_for_flask()
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	cmd = f'echo "show sess" |nc {server_ip} {haproxy_sock_port}'
	output, stderr = server_mod.subprocess_execute(cmd)

	return render_template('ajax/sessions_table.html', sessions=output, lang=lang)


def show_session(server_ip, sess_id) -> str:
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	cmd = f'echo "show sess {sess_id}" |nc {server_ip} {haproxy_sock_port}'
	output, stderr = server_mod.subprocess_execute(cmd)
	lines = ''

	if stderr:
		return 'error: ' + stderr[0]
	else:
		for o in output:
			lines += f'{o}<br />'
		return lines


def delete_session(server_ip, sess_id) -> str:
	haproxy_sock_port = sql.get_setting('haproxy_sock_port')
	cmd = f'echo "shutdown session {sess_id}" |nc {server_ip} {haproxy_sock_port}'
	output, stderr = server_mod.subprocess_execute(cmd)
	try:
		if output[0] != '':
			return 'error: ' + output[0]
	except Exception:
		pass
	try:
		if stderr[0] != '':
			return 'error: ' + stderr[0]
	except Exception:
		pass

	return 'ok'
