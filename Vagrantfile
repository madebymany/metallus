# -*- mode: ruby -*-
# vi: set ft=ruby :

Vagrant.configure(2) do |config|

  config.vm.define :metallus do |metallus|
    metallus.vm.provision "shell", path: "dependencies"
    metallus.vm.box = "ubuntu/trusty64"
    metallus.vm.hostname = "metallus"
    metallus.vm.network "public_network", :bridge => 'en0: Wi-Fi (AirPort)'
    metallus.vm.provider :virtualbox do |v|
      v.customize ["modifyvm", :id, "--memory", 1028]
    end
  end

end
