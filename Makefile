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

# was_active will be equal to 0 if the service is active at the moment of running this
was_active=$(shell systemctl is-active $(unit_name) > /dev/null 2>&1; echo $$?)

install:
	echo "Installing the service files..."
	cp diaspora.service $(service_dir)
	chown root:root $(service_dir)/diaspora.service
	chmod 644 $(service_dir)/diaspora.service

	-systemctl daemon-reload

ifeq ($(was_active), 0)
	echo "The service is running, apparently this is an upgrade.  Stopping the service before updating library files..."
	-systemctl stop $(unit_name)
	echo "Backing up the database..."
	cp $(data_dir)/people.db $(data_dir)/people.db.bck
else
	echo "The service is not running."
endif

	echo "Cleaning up library files before installing the new version..."
	-rm -r $(lib_dir) > /dev/null 2>&1

	echo "Installing library files..."
	cd src; find . -name '*.json' | cpio -pdm --quiet $(lib_dir)
	cd src; find . -name '*.mo' | cpio -pdm --quiet $(lib_dir)
	cd src; find . -name '*.py' | cpio -pdm --quiet $(lib_dir)
	cd src; find . -name '*.txt' | cpio -pdm --quiet $(lib_dir)

	chown root:root $(lib_dir)/*
	chmod 644 $(lib_dir)

	echo "Installing configuration files..."
	mkdir -p $(conf_dir)
	cp diaspora.env $(conf_dir)
	chown root:root $(conf_dir)/*
	chmod 644 $(conf_dir)

	echo "Preparing persistent storage..."
	mkdir -p $(data_dir)

	echo "Creating virtual environment for Python 3.12 and installing packages..."
	python3.12 -m venv $(venv) > /dev/null
	$(venv)/bin/pip3 install -r requirements.txt > /dev/null

	echo "Creating the initial configuration..."
	DIASPORA_SERVICE_MODE=1 $(venv)/bin/python $(lib_dir)/setup.py

ifeq ($(was_active), 0)
	echo "Starting the service again (we stopped it before updating library files)..."
	-systemctl start $(unit_name)
else
	echo "The service was not running when installation started, keeping it stopped."
endif

	echo "----------------------------------------------------------------"
	echo "Installation complete."
	echo "- Run 'systemctl {start|stop|restart|status} $(unit_name)' to control the service."
	echo "- The service configuration file is $(conf_dir)/settings.yaml.  Restart the service after editing it."
	echo "----------------------------------------------------------------"

uninstall:
	echo "Stopping and disabling the service..."
	-systemctl stop $(unit_name)
	-systemctl disable $(unit_name)
	echo "Deleting library files..."
	-rm -r $(lib_dir)
	echo "Deleting service files..."
	-rm -r $(service_dir)/diaspora.service
	echo "Uninstallation complete."

purge: uninstall
	echo "Deleting persistent data..."
	-rm -r $(data_dir)
	echo "Deleting configuration files..."
	-rm -r $(conf_dir)
	echo "Purge complete."
