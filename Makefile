# Installs or uninstalls the bot as a Linux systemd service

help:
	echo This script sets up the Diaspora Telegram bot as a systemd service, or removes that service.
	echo Please make one of the following targets.  Note that you will need superuser privileges.
	echo - install: install the bot as a systemd service.  The bot must be configured in direct mode beforehand.
	echo - uninstall: uninstall the service but keep configuration and data
	echo - purge: uninstall the service and delete configuration and data
	echo Please refer to README.md for more information on how to configure the bot.

.SILENT:

unit_name=diaspora

conf_dir=/usr/local/etc/${unit_name}
data_dir=/var/local/${unit_name}
lib_dir=/usr/local/lib/${unit_name}
service_dir=/etc/systemd/system

venv=${lib_dir}/venv

install: $(service_dir) diaspora.service src/settings.yaml
	echo Installing the service files...
	cp diaspora.service $(service_dir)
	chown root:root $(service_dir)/diaspora.service
	chmod 644 $(service_dir)/diaspora.service

	echo Installing library files...
	cd src; find . -name '*.mo' | cpio -pdm $(lib_dir)
	cd src; find . -name '*.py' | cpio -pdm $(lib_dir)

	chown root:root $(lib_dir)/*
	chmod 644 $(lib_dir)

	echo Installing configuration files...
	mkdir -p $(conf_dir)
	cp diaspora.env $(conf_dir)
	cp src/settings.yaml $(conf_dir)
	chown root:root $(conf_dir)/*
	chmod 644 $(conf_dir)

	echo Preparing persistent storage...
	mkdir -p $(data_dir)
	cp src/people.db $(data_dir)

	echo Creating virtual environment for Python 3.12 and installing packages...
	python3.12 -m venv $(venv)
	$(venv)/bin/pip3 install -r requirements.txt

	echo Installation complete.
	echo run 'systemctl start diaspora' to start the service
	echo run 'systemctl status diaspora' to view status
	echo run 'systemctl stop diaspora' to stop the service

uninstall:
	echo Stopping and disabling the service...
	-systemctl stop diaspora
	-systemctl disable diaspora
	echo Deleting library files...
	-rm -r $(lib_dir)
	echo Deleting service files...
	-rm -r $(service_dir)/diaspora.service
	echo Uninstallation complete.

purge: uninstall
	echo Deleting persistent data...
	-rm -r $(data_dir)
	echo Deleting configuration files...
	-rm -r $(conf_dir)
	echo Purge complete.
