// SPDX-License-Identifier: AGPL-3.0
pragma solidity ^0.8.15;

// These are the core Yearn libraries
import "@openzeppelin/contracts/utils/math/Math.sol";
import "./interfaces/yearn.sol";
import "./interfaces/curve.sol";
import "@yearnvaults/contracts/BaseStrategy.sol";

interface ITradeFactory {
    function enable(address, address) external;

    function disable(address, address) external;
}

interface IDetails {
    // get details from curve
    function name() external view returns (string memory);

    function symbol() external view returns (string memory);
}

contract StrategyRamsesBoostedFactoryClonable is BaseStrategy {
    using SafeERC20 for IERC20;

    // Tokens used
    address public native;
    address public output;
    address public want;
    address public lpToken0;
    address public lpToken1;

    // Third party contracts
    address public gauge;
    address public gaugeStaker;

    address[] public rewards;

    bool public stable;
    bool public harvestOnDeposit;
    bool public spiritHarvest;
    uint256 public lastHarvest;

    // Routes
    ISolidlyRouter.Routes[] public outputToNativeRoute;
    ISolidlyRouter.Routes[] public routeToken0;
    ISolidlyRouter.Routes[] public routeToken1;
    
    /* ========== STATE VARIABLES ========== */

    /// @notice Yearn's strategyProxy, needed for interacting with our Curve Voter.
    ICurveStrategyProxy public proxy;

    /// @notice Curve gauge contract, most are tokenized, held by Yearn's voter.
    address public gauge;

    /// @notice The percentage of CRV from each harvest that we send to our voter (out of 10,000).
    uint256 public localKeepCRV;

    /// @notice The address of our Curve voter. This is where we send any keepCRV.
    address public curveVoter;

    // this means all of our fee values are in basis points
    uint256 internal constant FEE_DENOMINATOR = 10000;

    /// @notice The address of our base token (CRV for Curve, BAL for Balancer, etc.).
    IERC20 public constant crv =
        IERC20(0xAAA6C1E32C55A7Bfa8066A6FAE9b42650F262418);

    // we use this to be able to adjust our strategy's name
    string internal stratName;

    /// @notice Will only be true on the original deployed contract and not on clones; we don't want to clone a clone.
    bool public isOriginal = true;

    /* ========== CONSTRUCTOR ========== */

    constructor(
        address _vault,
        address _proxy,
        address _gauge
    ) BaseStrategy(_vault) {
        _initializeStrat(_proxy, _gauge);
    }

    /* ========== CLONING ========== */

    event Cloned(address indexed clone);

    /// @notice Use this to clone an exact copy of this strategy on another vault.
    /// @dev In practice, this will only be called by the factory on the template contract.
    /// @param _vault Vault address we are targeting with this strategy.
    /// @param _strategist Address to grant the strategist role.
    /// @param _rewards If we have any strategist rewards, send them here.
    /// @param _keeper Address to grant the keeper role.
    /// @param _proxy Our strategy proxy address.
    /// @param _gauge Gauge address for this strategy.
    /// @return newStrategy Address of our new cloned strategy.
    function cloneStrategyCurveBoosted(
        address _vault,
        address _strategist,
        address _rewards,
        address _keeper,
        address _proxy,
        address _gauge
    ) external returns (address newStrategy) {
        // don't clone a clone
        if (!isOriginal) {
            revert();
        }

        // Copied from https://github.com/optionality/clone-factory/blob/master/contracts/CloneFactory.sol
        bytes20 addressBytes = bytes20(address(this));
        assembly {
            // EIP-1167 bytecode
            let clone_code := mload(0x40)
            mstore(
                clone_code,
                0x3d602d80600a3d3981f3363d3d373d3d3d363d73000000000000000000000000
            )
            mstore(add(clone_code, 0x14), addressBytes)
            mstore(
                add(clone_code, 0x28),
                0x5af43d82803e903d91602b57fd5bf30000000000000000000000000000000000
            )
            newStrategy := create(0, clone_code, 0x37)
        }

        StrategyCurveBoostedFactoryClonable(newStrategy).initialize(
            _vault,
            _strategist,
            _rewards,
            _keeper,
            _proxy,
            _gauge
        );

        emit Cloned(newStrategy);
    }

    /// @notice Initialize the strategy.
    /// @dev This should only be called by the clone function above.
    /// @param _vault Vault address we are targeting with this strategy.
    /// @param _strategist Address to grant the strategist role.
    /// @param _rewards If we have any strategist rewards, send them here.
    /// @param _keeper Address to grant the keeper role.
    /// @param _proxy Our strategy proxy address.
    /// @param _gauge Gauge address for this strategy.
    function initialize(
        address _vault,
        address _strategist,
        address _rewards,
        address _keeper,
        address _proxy,
        address _gauge
    ) public {
        _initialize(_vault, _strategist, _rewards, _keeper);
        _initializeStrat(_proxy, _gauge);
    }

    // this is called by our original strategy, as well as any clones
    function _initializeStrat(
        address _proxy,
        address _gauge
    ) internal {
        // make sure that we haven't initialized this before
        if (gauge != address(0)) {
            revert(); // already initialized.
        }

        // 1:1 assignments
        proxy = ICurveStrategyProxy(_proxy); // our factory checks the latest proxy from curve voter and passes it here
        gauge = _gauge;

        // want = Curve LP
        want.approve(_proxy, type(uint256).max);

        // set up our baseStrategy vars
        minReportDelay = 21 days;
        maxReportDelay = 365 days;
        creditThreshold = 50_000e18;

        // set our strategy's name
        stratName = string(
            abi.encodePacked(
                "StrategyRamsesBoostedFactory-",
                IDetails(address(want)).symbol()
            )
        );
    }

    function initialize(
        address _want,
        address _gauge,
        ISolidlyRouter.Routes[] memory _outputToNativeRoute,
        ISolidlyRouter.Routes[] memory _outputToLp0Route,
        ISolidlyRouter.Routes[] memory _outputToLp1Route
    ) public initializer  {
        want = _want;
        gauge = _gauge;

        stable = ISolidlyPair(_want).stable();

        for (uint i; i < _outputToNativeRoute.length; ++i) {
            outputToNativeRoute.push(_outputToNativeRoute[i]);
        }

        for (uint i; i < _outputToLp0Route.length; ++i) {
            outputToLp0Route.push(_outputToLp0Route[i]);
        }

        for (uint i; i < _outputToLp1Route.length; ++i) {
            outputToLp1Route.push(_outputToLp1Route[i]);
        }

        output = outputToNativeRoute[0].from;
        native = outputToNativeRoute[outputToNativeRoute.length - 1].to;
        lpToken0 = outputToLp0Route[outputToLp0Route.length - 1].to;
        lpToken1 = outputToLp1Route[outputToLp1Route.length - 1].to;
        rewards.push(output);

        _giveAllowances();
    }

    /* ========== VIEWS ========== */

    /// @notice Strategy name.
    function name() external view override returns (string memory) {
        return stratName;
    }

    /// @notice Balance of want staked in Curve's gauge.
    function stakedBalance() public view returns (uint256) {
        return proxy.balanceOf(gauge);
    }

    /// @notice Balance of want sitting in our strategy.
    function balanceOfWant() public view returns (uint256) {
        return want.balanceOf(address(this));
    }

    /// @notice Total assets the strategy holds, sum of loose and staked want.
    function estimatedTotalAssets() public view override returns (uint256) {
        return balanceOfWant() + stakedBalance();
    }

    function _solidlyToRoute(ISolidlyRouter.Routes[] memory _route) internal pure returns (address[] memory) {
        address[] memory route = new address[](_route.length + 1);
        route[0] = _route[0].from;
        for (uint i; i < _route.length; ++i) {
            route[i + 1] = _route[i].to;
        }
        return route;
    }

    function outputToNative() external view returns (address[] memory) {
        ISolidlyRouter.Routes[] memory _route = outputToNativeRoute;
        return _solidlyToRoute(_route);
    }

    function outputToLp0() external view returns (address[] memory) {
        ISolidlyRouter.Routes[] memory _route = outputToLp0Route;
        return _solidlyToRoute(_route);
    }

    function outputToLp1() external view returns (address[] memory) {
        ISolidlyRouter.Routes[] memory _route = outputToLp1Route;
        return _solidlyToRoute(_route);
    }

    // calculate the total underlaying 'want' held by the strat.
    function balanceOf() public view returns (uint256) {
        return balanceOfWant() + balanceOfPool();
    }

    // it calculates how much 'want' this contract holds.
    function balanceOfWant() public view returns (uint256) {
        return IERC20(want).balanceOf(address(this));
    }

    // it calculates how much 'want' the strategy has working in the farm.
    function balanceOfPool() public view returns (uint256) {
        uint256 _amount = IGauge(gauge).balanceOf(gaugeStaker);
        return _amount;
    }

    // returns rewards unharvested
    function rewardsAvailable() public view returns (uint256) {
        return spiritHarvest ? IGauge(gauge).earned(gaugeStaker) : IGauge(gauge).earned(output, gaugeStaker);
    }

    // native reward amount for calling harvest
    function callReward() public view returns (uint256) {
        IFeeConfig.FeeCategory memory fees = getFees();
        uint256 outputBal = rewardsAvailable();
        uint256 nativeOut;
        if (outputBal > 0) {
            (nativeOut,) = ISolidlyRouter(unirouter).getAmountOut(outputBal, output, native);
        }

        return nativeOut * fees.total / DIVISOR * fees.call / DIVISOR;
    }

    /* ========== CORE STRATEGY FUNCTIONS ========== */

    function prepareReturn(
        uint256 _debtOutstanding
    )
        internal
        override
        returns (uint256 _profit, uint256 _loss, uint256 _debtPayment)
    {
        // rewards will be converted later with mev protection by yswaps (tradeFactory)
        
        // claim our rewards
        IGaugeStaker(gaugeStaker).claimGaugeReward(gauge)
        
        // sell rewards for more want, have to add from both sides
        uint256 ramBalance = ram.balanceOf(address(this));
        uint256 amountToSwapToken0 = ramBalance / 2;
        uint256 amountToSwapToken1 = ramBalance - amountToken0;
        
        // if stable, do some more fancy math
        if (isStablePair) {
            (amountToSwapToken0, amountToSwapToken1) = _doStableMath(ramBalance, amountToSwapToken0, amountToSwapToken1);
        }

        if (address(token0) != address(ram)) {
            ISolidlyRouter(unirouter).swapExactTokensForTokens(amountToSwapToken0, 0, routeToken0, address(this), block.timestamp);
        }

        if (address(token1) != address(ram)) {
            ISolidlyRouter(unirouter).swapExactTokensForTokens(amountToSwapToken1, 0, routeToken1, address(this), block.timestamp);
        }

        uint256 balanceToken0 = token0.balanceOf(address(this));
        uint256 balanceToken1 = token1.balanceOf(address(this));
        router.addLiquidity(address(token0), address(token1), isStablePair, balanceToken0, balanceToken1, 1, 1, address(this), block.timestamp);

        // serious loss should never happen, but if it does (for instance, if Curve is hacked), let's record it accurately
        uint256 assets = estimatedTotalAssets();
        uint256 debt = vault.strategies(address(this)).totalDebt;

        // if assets are greater than debt, things are working great!
        if (assets >= debt) {
            unchecked {
                _profit = assets - debt;
            }
            _debtPayment = _debtOutstanding;

            uint256 toFree = _profit + _debtPayment;

            // freed is math.min(wantBalance, toFree)
            (uint256 freed, ) = liquidatePosition(toFree);

            if (toFree > freed) {
                if (_debtPayment > freed) {
                    _debtPayment = freed;
                    _profit = 0;
                } else {
                    unchecked {
                        _profit = freed - _debtPayment;
                    }
                }
            }
        }
        // if assets are less than debt, we are in trouble. don't worry about withdrawing here, just report losses
        else {
            unchecked {
                _loss = debt - assets;
            }
        }
    }

    // Adds liquidity to AMM and gets more LP tokens.
    function _doStableMath(uint256 _ramBalance, uint256 _token0Amount, uint256 _token1Amount) internal return (uint256, uint256) {
        uint256 decimalsToken0 = 10**token0.decimals();
        uint256 decimalsToken1 = 10**token1.decimals();
        
        // get our anticipated amounts out
        uint256 amountsOut0 = router.getAmountsOut(_token0Amount, outputToLp0Route)[outputToLp0Route.length] * 1e18 / decimalsToken0;
        uint256 amountsOut1 = router.getAmountsOut(_token1Amount, outputToLp1Route)[outputToLp1Route.length] * 1e18 / decimalsToken1;
        (uint256 amountA, uint256 amountB,) = router.quoteAddLiquidity(address(token0), address(token1), true, amountsOut0, amountsOut1);
        amountA = amountA * 1e18 / lp0Decimals;
        amountB = amountB * 1e18 / lp1Decimals;
        uint256 ratio = amountsOut0 * 1e18 / amountsOut1 * amountB / amountA;
        amountsOut0 = _ramBalance * 1e18 / (ratio + 1e18);
        amountsOut1 = _ramBalance - amountsOut0;
        return (amountsOut0, amountsOut1);     
    }

    function adjustPosition(uint256 _debtOutstanding) internal override {
        // if in emergency exit, we don't want to deploy any more funds
        if (emergencyExit) {
            return;
        }

        // Send all of our LP tokens to the proxy and deposit to the gauge
        uint256 _toInvest = balanceOfWant();
        if (_toInvest > 0) {
            want.safeTransfer(address(proxy), _toInvest);
            proxy.deposit(gauge, address(want));
        }
    }

    function liquidatePosition(
        uint256 _amountNeeded
    ) internal override returns (uint256 _liquidatedAmount, uint256 _loss) {
        // check our loose want
        uint256 _wantBal = balanceOfWant();
        if (_amountNeeded > _wantBal) {
            uint256 _stakedBal = stakedBalance();
            if (_stakedBal > 0) {
                uint256 _neededFromStaked;
                unchecked {
                    _neededFromStaked = _amountNeeded - _wantBal;
                }
                // withdraw whatever extra funds we need
                proxy.withdraw(
                    gauge,
                    address(want),
                    Math.min(_stakedBal, _neededFromStaked)
                );
            }
            uint256 _withdrawnBal = balanceOfWant();
            _liquidatedAmount = Math.min(_amountNeeded, _withdrawnBal);
            unchecked {
                _loss = _amountNeeded - _liquidatedAmount;
            }
        } else {
            // we have enough balance to cover the liquidation available
            return (_amountNeeded, 0);
        }
    }

    // fire sale, get rid of it all!
    function liquidateAllPositions() internal override returns (uint256) {
        uint256 _stakedBal = stakedBalance();
        if (_stakedBal > 0) {
            // don't bother withdrawing zero, save gas where we can
            proxy.withdraw(gauge, address(want), _stakedBal);
        }
        return balanceOfWant();
    }

    // migrate our want token to a new strategy if needed, as well as our CRV
    function prepareMigration(address _newStrategy) internal override {
        uint256 stakedBal = stakedBalance();
        if (stakedBal > 0) {
            proxy.withdraw(gauge, address(want), stakedBal);
        }
        uint256 crvBal = crv.balanceOf(address(this));

        if (crvBal > 0) {
            crv.safeTransfer(_newStrategy, crvBal);
        }
    }

    // want is blocked by default, add any other tokens to protect from gov here.
    function protectedTokens()
        internal
        view
        override
        returns (address[] memory)
    {}

    /* ========== YSWAPS ========== */

    /// @notice Use to add or update rewards, rebuilds tradefactory too
    /// @dev Do this before updating trade factory if we have extra rewards.
    ///  Can only be called by governance.
    /// @param _rewards Rewards tokens to add to our trade factory.
    function updateRewards(address[] memory _rewards) external onlyGovernance {
        address tf = tradeFactory;
        _removeTradeFactoryPermissions(true);
        rewardsTokens = _rewards;

        tradeFactory = tf;
        _setUpTradeFactory();
    }

    /// @notice Use to update our trade factory.
    /// @dev Can only be called by governance.
    /// @param _newTradeFactory Address of new trade factory.
    function updateTradeFactory(
        address _newTradeFactory
    ) external onlyGovernance {
        require(
            _newTradeFactory != address(0),
            "Can't remove with this function"
        );
        _removeTradeFactoryPermissions(true);
        tradeFactory = _newTradeFactory;
        _setUpTradeFactory();
    }

    function _setUpTradeFactory() internal {
        // approve and set up trade factory
        address _tradeFactory = tradeFactory;
        address _want = address(want);

        ITradeFactory tf = ITradeFactory(_tradeFactory);
        crv.approve(_tradeFactory, type(uint256).max);
        tf.enable(address(crv), _want);

        // enable for all rewards tokens too
        for (uint256 i; i < rewardsTokens.length; ++i) {
            address _rewardsToken = rewardsTokens[i];
            IERC20(_rewardsToken).approve(_tradeFactory, type(uint256).max);
            tf.enable(_rewardsToken, _want);
        }
    }

    /// @notice Use this to remove permissions from our current trade factory.
    /// @dev Once this is called, setUpTradeFactory must be called to get things working again.
    /// @param _disableTf Specify whether to disable the tradefactory when removing.
    ///  Option given in case we need to get around a reverting disable.
    function removeTradeFactoryPermissions(
        bool _disableTf
    ) external onlyVaultManagers {
        _removeTradeFactoryPermissions(_disableTf);
    }

    function _removeTradeFactoryPermissions(bool _disableTf) internal {
        address _tradeFactory = tradeFactory;
        if (_tradeFactory == address(0)) {
            return;
        }
        ITradeFactory tf = ITradeFactory(_tradeFactory);

        address _want = address(want);
        crv.approve(_tradeFactory, 0);
        if (_disableTf) {
            tf.disable(address(crv), _want);
        }

        // disable for all rewards tokens too
        for (uint256 i; i < rewardsTokens.length; ++i) {
            address _rewardsToken = rewardsTokens[i];
            IERC20(_rewardsToken).approve(_tradeFactory, 0);
            if (_disableTf) {
                tf.disable(_rewardsToken, _want);
            }
        }

        tradeFactory = address(0);
    }

    /* ========== KEEP3RS ========== */

    /**
     * @notice
     *  Provide a signal to the keeper that harvest() should be called.
     *
     *  Don't harvest if a strategy is inactive.
     *  If we exceed our max delay, then harvest no matter what. For
     *  our min delay, credit threshold, and manual force trigger,
     *  only harvest if our gas price is acceptable.
     *
     * @param callCostinEth The keeper's estimated gas cost to call harvest() (in wei).
     * @return True if harvest() should be called, false otherwise.
     */
    function harvestTrigger(
        uint256 callCostinEth
    ) public view override returns (bool) {
        // Should not trigger if strategy is not active (no assets and no debtRatio). This means we don't need to adjust keeper job.
        if (!isActive()) {
            return false;
        }

        StrategyParams memory params = vault.strategies(address(this));
        // harvest no matter what once we reach our maxDelay
        if (block.timestamp - params.lastReport > maxReportDelay) {
            return true;
        }

        // check if the base fee gas price is higher than we allow. if it is, block harvests.
        if (!isBaseFeeAcceptable()) {
            return false;
        }

        // trigger if we want to manually harvest, but only if our gas price is acceptable
        if (forceHarvestTriggerOnce) {
            return true;
        }

        // harvest if we hit our minDelay, but only if our gas price is acceptable
        if (block.timestamp - params.lastReport > minReportDelay) {
            return true;
        }

        // harvest our credit if it's above our threshold
        if (vault.creditAvailable() > creditThreshold) {
            return true;
        }

        // otherwise, we don't harvest
        return false;
    }

    /// @notice Convert our keeper's eth cost into want
    /// @dev We don't use this since we don't factor call cost into our harvestTrigger.
    /// @param _ethAmount Amount of ether spent.
    /// @return Value of ether in want.
    function ethToWant(
        uint256 _ethAmount
    ) public view override returns (uint256) {}

    /* ========== SETTERS ========== */
    // These functions are useful for setting parameters of the strategy that may need to be adjusted.

    /// @notice Use this to set or update our keep amounts for this strategy.
    /// @dev Must be less than 10,000. Set in basis points. Only governance can set this.
    /// @param _keepCrv Percent of each CRV harvest to send to our voter.
    function setLocalKeepCrv(uint256 _keepCrv) external onlyGovernance {
        if (_keepCrv > 10_000) {
            revert();
        }
        if (_keepCrv > 0 && curveVoter == address(0)) {
            revert();
        }
        localKeepCRV = _keepCrv;
    }

    /// @notice Use this to set or update our voter contracts.
    /// @dev For Curve strategies, this is where we send our keepCVX.
    ///  Only governance can set this.
    /// @param _curveVoter Address of our curve voter.
    function setVoter(address _curveVoter) external onlyGovernance {
        curveVoter = _curveVoter;
    }
}
