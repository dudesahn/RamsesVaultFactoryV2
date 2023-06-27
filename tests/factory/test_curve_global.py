import brownie
from brownie import Contract, ZERO_ADDRESS, interface, chain, accounts
import math
import pytest


def test_vault_deployment(
    StrategyVelodromeFactoryClonable,
    strategist,
    velo_global,
    gov,
    guardian,
    token,
    health_check,
    base_fee_oracle,
    new_registry,
    gauge,
    whale,
    tests_using_tenderly,
    amount,
    route0,
    route1,
    keeper_wrapper,
):
    # once our factory is deployed, setup the factory from gov
    registry_owner = accounts.at(new_registry.owner(), force=True)
    new_registry.setApprovedVaultsOwner(velo_global, True, {"from": registry_owner})
    new_registry.setVaultEndorsers(velo_global, True, {"from": registry_owner})

    # make sure our curve global can own vaults and endorse them
    assert new_registry.approvedVaultsOwner(velo_global)
    assert new_registry.vaultEndorsers(velo_global)
    assert velo_global.registry() == new_registry.address
    print("Our factory can endorse vaults")

    print("Let's deploy this vault")
    print("Factory address: ", velo_global)
    print("Gauge: ", gauge)

    # make sure we can create this vault permissionlessly
    assert velo_global.canCreateVaultPermissionlessly(gauge)

    # turn on keeps
    velo_global.setKeepVELO(69, velo_global.veloVoter(), {"from": gov})
    print(
        "Set our global keeps, don't mess with curve voter or we will revert on deploy"
    )

    tx = velo_global.createNewVaultsAndStrategies(
        gauge, route0, route1, {"from": whale}
    )
    assert velo_global.latestStandardVaultFromGauge(gauge) != ZERO_ADDRESS

    vault_address = tx.events["NewAutomatedVault"]["vault"]
    vault = Contract(vault_address)
    print("Vault name:", vault.name())

    print("Vault endorsed:", vault_address)
    info = tx.events["NewAutomatedVault"]

    print("Here's our new vault created event:", info, "\n")

    # check that everything is setup properly for our vault
    assert vault.governance() == velo_global.address
    assert vault.management() == velo_global.management()
    assert vault.guardian() == velo_global.guardian()
    assert vault.guardian() == velo_global.guardian()
    assert vault.depositLimit() == velo_global.depositLimit()
    assert vault.rewards() == velo_global.treasury()
    assert vault.managementFee() == velo_global.managementFee()
    assert vault.performanceFee() == velo_global.performanceFee()

    # check that things are good on our strategies
    velo_strat = tx.events["NewAutomatedVault"]["velodromeStrategy"]
    velo_strategy = StrategyVelodromeFactoryClonable.at(velo_strat)
    assert vault.withdrawalQueue(0) == velo_strat
    assert vault.strategies(velo_strat)["performanceFee"] == 0
    assert velo_strategy.creditThreshold() == 5e22
    assert velo_strategy.healthCheck() == velo_global.healthCheck()
    assert velo_strategy.localKeepVELO() == velo_global.keepVELO()
    assert velo_strategy.veloVoter() == velo_global.veloVoter()
    assert velo_strategy.rewards() == velo_global.treasury()
    assert velo_strategy.strategist() == velo_global.management()
    assert velo_strategy.keeper() == velo_global.keeper()

    # daddy needs to accept gov on all new vaults
    vault.acceptGovernance({"from": gov})
    assert vault.governance() == gov.address

    # check that anyone can harvest a strategy thanks to our keeper wrapper
    print(
        "Check out our keeper wrapper, make sure it works as intended for all strategies"
    )
    rando = accounts[5]
    assert velo_strategy.keeper() == keeper_wrapper
    ## deposit to the vault after approving
    startingWhale = token.balanceOf(whale)
    token.approve(vault, 2**256 - 1, {"from": whale})
    vault.deposit(amount, {"from": whale})

    keeper_wrapper.harvest(velo_strategy, {"from": rando})
    if velo_strat != ZERO_ADDRESS:
        keeper_wrapper.harvest(velo_strategy, {"from": rando})

    # assert that money deposited to convex
    assert velo_strategy.stakedBalance() > 0

    assert not velo_global.canCreateVaultPermissionlessly(gauge)
    assert velo_global.latestStandardVaultFromGauge(gauge) != ZERO_ADDRESS
    print("Can't create another of the same vault permissionlessly")

    if not tests_using_tenderly:
        # can't deploy another of the same vault permissionlessly
        with brownie.reverts("Vault already exists"):
            tx = velo_global.createNewVaultsAndStrategies(
                gauge, route0, route1, {"from": whale}
            )
        # can't deploy a vault for something that's not a gauge
        with brownie.reverts():
            tx = velo_global.createNewVaultsAndStrategies(
                whale, route0, route1, {"from": whale}
            )


def test_permissioned_vault(
    StrategyVelodromeFactoryClonable,
    strategist,
    velo_global,
    gov,
    guardian,
    token,
    health_check,
    base_fee_oracle,
    new_registry,
    gauge,
    whale,
    tests_using_tenderly,
    route0,
    route1,
):
    # deploying curve global with frax strategies doesn't work unless with tenderly;
    # ganache crashes because of the try-catch in the fraxPid function
    # however, I usually do hacky coverage testing (commenting out section in curveGlobal)

    # once our factory is deployed, setup the factory from gov
    registry_owner = accounts.at(new_registry.owner(), force=True)
    new_registry.setApprovedVaultsOwner(velo_global, True, {"from": registry_owner})
    new_registry.setVaultEndorsers(velo_global, True, {"from": registry_owner})

    # make sure our curve global can own vaults and endorse them
    assert new_registry.approvedVaultsOwner(velo_global)
    assert new_registry.vaultEndorsers(velo_global)
    assert velo_global.registry() == new_registry.address
    print("Our factory can endorse vaults")

    print("Let's deploy this vault")
    print("Factory address: ", velo_global)
    print("Gauge: ", gauge)

    # check if we can create this vault permissionlessly
    print(
        "Can we create this vault permissionlessly?",
        velo_global.canCreateVaultPermissionlessly(gauge),
    )

    # turn on keeps
    velo_global.setKeepVELO(69, gov.address, {"from": gov})
    assert velo_global.keepVELO() > 0

    # make sure not just anyone can create a permissioned vault
    if not tests_using_tenderly:
        with brownie.reverts():
            velo_global.createNewVaultsAndStrategiesPermissioned(
                gauge, route0, route1, "poop", "poop", {"from": whale}
            )

    if not tests_using_tenderly:
        with brownie.reverts():
            velo_global.createNewVaultsAndStrategiesPermissioned(
                health_check,
                route0,
                route1,
                "poop",
                "poop",
                {"from": velo_global.management()},
            )
        print("Can't create a vault for something that's not actually a gauge")

    # we can't create a vault for something that doesn't have a gauge

    tx = velo_global.createNewVaultsAndStrategiesPermissioned(
        gauge, route0, route1, "stuff", "stuff", {"from": gov}
    )

    vault_address = tx.events["NewAutomatedVault"]["vault"]
    vault = Contract(vault_address)
    print("Vault name:", vault.name())

    print("Vault endorsed:", vault_address)
    info = tx.events["NewAutomatedVault"]

    print("Here's our new vault created event:", info, "\n")

    # check that everything is setup properly for our vault
    assert vault.governance() == velo_global.address
    assert vault.management() == velo_global.management()
    assert vault.guardian() == velo_global.guardian()
    assert vault.guardian() == velo_global.guardian()
    assert vault.depositLimit() == velo_global.depositLimit()
    assert vault.rewards() == velo_global.treasury()
    assert vault.managementFee() == velo_global.managementFee()
    assert vault.performanceFee() == velo_global.performanceFee()

    # check that things are good on our strategies
    velo_strat = tx.events["NewAutomatedVault"]["velodromeStrategy"]
    velo_strategy = StrategyVelodromeFactoryClonable.at(velo_strat)
    assert vault.withdrawalQueue(0) == velo_strat
    assert vault.strategies(velo_strat)["performanceFee"] == 0
    assert velo_strategy.creditThreshold() == 5e22
    assert velo_strategy.healthCheck() == velo_global.healthCheck()
    assert velo_strategy.localKeepVELO() == velo_global.keepVELO()
    assert velo_strategy.veloVoter() == velo_global.veloVoter()
    assert velo_strategy.rewards() == velo_global.treasury()
    assert velo_strategy.strategist() == velo_global.management()
    assert velo_strategy.keeper() == velo_global.keeper()

    # daddy needs to accept gov on all new vaults
    vault.acceptGovernance({"from": gov})
    assert vault.governance() == gov.address
    print("Gov accepted by daddy")


def test_velo_global_setters_and_views(
    gov,
    whale,
    amount,
    velo_global,
    new_registry,
    gauge,
    token,
):

    # once our factory is deployed, setup the factory from gov
    registry_owner = accounts.at(new_registry.owner(), force=True)
    new_registry.setApprovedVaultsOwner(velo_global, True, {"from": registry_owner})
    new_registry.setVaultEndorsers(velo_global, True, {"from": registry_owner})

    # make sure our curve global can own vaults and endorse them
    assert new_registry.approvedVaultsOwner(velo_global)
    assert new_registry.vaultEndorsers(velo_global)
    print("Our factory can endorse vaults")

    # check our views
    print("Time to check the views")

    # check our deployed vaults
    all_vaults = velo_global.allDeployedVaults()
    print("All vaults:", all_vaults)

    length = velo_global.numVaults()
    print("Number of vaults:", length)

    # this one should always be yes (BLU/USDC) as we will almost certainly never make a vault for this
    assert velo_global.canCreateVaultPermissionlessly(
        "0x8166f06D50a65F82850878c951fcA29Af5Ea7Db2"
    )

    # check our latest vault
    latest = velo_global.latestStandardVaultFromGauge(gauge)
    print("Latest FUD vault:", latest)

    # check our setters
    with brownie.reverts():
        velo_global.setKeepVELO(69, gov, {"from": whale})
    velo_global.setKeepVELO(0, gov, {"from": gov})
    velo_global.setKeepVELO(69, gov, {"from": gov})
    assert velo_global.keepVELO() == 69
    assert velo_global.veloVoter() == gov.address
    with brownie.reverts():
        velo_global.setKeepVELO(69, ZERO_ADDRESS, {"from": gov})
    with brownie.reverts():
        velo_global.setKeepVELO(10_001, gov, {"from": gov})

    with brownie.reverts():
        velo_global.setDepositLimit(69, {"from": whale})
    velo_global.setDepositLimit(0, {"from": gov})
    velo_global.setDepositLimit(69, {"from": velo_global.management()})
    assert velo_global.depositLimit() == 69

    with brownie.reverts():
        velo_global.setHarvestProfitMaxInUsdc(69, {"from": whale})
    velo_global.setHarvestProfitMaxInUsdc(0, {"from": gov})
    velo_global.setHarvestProfitMaxInUsdc(69, {"from": velo_global.management()})
    assert velo_global.harvestProfitMaxInUsdc() == 69

    with brownie.reverts():
        velo_global.setHarvestProfitMinInUsdc(69, {"from": whale})
    velo_global.setHarvestProfitMinInUsdc(0, {"from": gov})
    velo_global.setHarvestProfitMinInUsdc(69, {"from": velo_global.management()})
    assert velo_global.harvestProfitMinInUsdc() == 69

    with brownie.reverts():
        velo_global.setKeeper(gov, {"from": whale})
    velo_global.setKeeper(whale, {"from": gov})
    velo_global.setKeeper(gov, {"from": velo_global.management()})
    assert velo_global.keeper() == gov.address

    with brownie.reverts():
        velo_global.setHealthcheck(gov, {"from": whale})
    velo_global.setHealthcheck(whale, {"from": gov})
    velo_global.setHealthcheck(gov, {"from": velo_global.management()})
    assert velo_global.healthCheck() == gov.address

    with brownie.reverts():
        velo_global.setRegistry(gov, {"from": whale})
    velo_global.setRegistry(gov, {"from": gov})
    assert velo_global.registry() == gov.address

    with brownie.reverts():
        velo_global.setGuardian(gov, {"from": whale})
    velo_global.setGuardian(gov, {"from": gov})
    assert velo_global.guardian() == gov.address

    with brownie.reverts():
        velo_global.setGovernance(gov, {"from": whale})
    velo_global.setGovernance(gov, {"from": gov})
    assert velo_global.governance() == gov.address

    with brownie.reverts():
        velo_global.setManagement(gov, {"from": whale})
    velo_global.setManagement(gov, {"from": gov})
    assert velo_global.management() == gov.address

    with brownie.reverts():
        velo_global.setGuardian(gov, {"from": whale})
    velo_global.setGuardian(gov, {"from": gov})
    assert velo_global.guardian() == gov.address

    with brownie.reverts():
        velo_global.setTreasury(gov, {"from": whale})
    velo_global.setTreasury(gov, {"from": gov})
    assert velo_global.treasury() == gov.address

    velo_global.setBaseFeeOracle(gov, {"from": velo_global.management()})
    with brownie.reverts():
        velo_global.setBaseFeeOracle(gov, {"from": whale})
    velo_global.setBaseFeeOracle(gov, {"from": gov})
    assert velo_global.baseFeeOracle() == gov.address

    with brownie.reverts():
        velo_global.setVelodromeStratImplementation(gov, {"from": whale})
    velo_global.setVelodromeStratImplementation(gov, {"from": gov})
    assert velo_global.velodromeStratImplementation() == gov.address

    with brownie.reverts():
        velo_global.setManagementFee(69, {"from": whale})
    velo_global.setManagementFee(69, {"from": gov})
    assert velo_global.managementFee() == 69
    with brownie.reverts():
        velo_global.setManagementFee(9999, {"from": gov})

    with brownie.reverts():
        velo_global.setPerformanceFee(69, {"from": whale})
    velo_global.setPerformanceFee(69, {"from": gov})
    assert velo_global.performanceFee() == 69
    with brownie.reverts():
        velo_global.setPerformanceFee(9999, {"from": gov})

    with brownie.reverts():
        velo_global.setOwner(gov, {"from": whale})
    velo_global.setOwner(whale, {"from": gov})
    with brownie.reverts():
        velo_global.acceptOwner({"from": gov})
    velo_global.acceptOwner({"from": whale})
    assert velo_global.owner() == whale.address
