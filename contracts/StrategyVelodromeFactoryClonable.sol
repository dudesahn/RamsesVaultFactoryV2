// SPDX-License-Identifier: AGPL-3.0
pragma solidity ^0.8.15;

// These are the core Yearn libraries
import "@openzeppelin/contracts/utils/math/Math.sol";
import "@yearnvaults/contracts/BaseStrategy.sol";

interface IVelodromeRouter {
    struct Routes {
        address from;
        address to;
        bool stable;
        address factory;
    }

    function addLiquidity(
        address,
        address,
        bool,
        uint256,
        uint256,
        uint256,
        uint256,
        address,
        uint256
    ) external returns (uint256 amountA, uint256 amountB, uint256 liquidity);

    function swapExactTokensForTokens(
        uint256 amountIn,
        uint256 amountOutMin,
        Routes[] memory routes,
        address to,
        uint256 deadline
    ) external returns (uint256[] memory amounts);

    function quoteStableLiquidityRatio(
        address token0,
        address token1,
        address factory
    ) external view returns (uint256 ratio);
}

interface IVelodromeGauge {
    function deposit(uint256 amount) external;

    function balanceOf(address) external view returns (uint256);

    function withdraw(uint256 amount) external;

    function getReward(address account) external;

    function earned(address account) external view returns (uint256);

    function stakingToken() external view returns (address);
}

interface IVelodromePool {
    function stable() external view returns (bool);

    function token0() external view returns (address);

    function token1() external view returns (address);

    function factory() external view returns (address);

    function getAmountOut(
        uint256 amountIn,
        address tokenIn
    ) external view returns (uint256 amount);
}

interface IDetails {
    // get details from curve
    function name() external view returns (string memory);

    function symbol() external view returns (string memory);
}

contract StrategyVelodromeFactoryClonable is BaseStrategy {
    using SafeERC20 for IERC20;

    /* ========== STATE VARIABLES ========== */

    /// @notice Velodrome gauge contract
    IVelodromeGauge public gauge;

    /// @notice Velodrome v2 router contract
    IVelodromeRouter public constant router =
        IVelodromeRouter(0xa062aE8A9c5e11aaA026fc2670B0D65cCc8B2858);

    /// @notice The percentage of VELO from each harvest that we send to our voter (out of 10,000).
    uint256 public localKeepVELO;

    /// @notice The address of our Velodrome voter. This is where we send any keepVELO.
    address public veloVoter;

    // this means all of our fee values are in basis points
    uint256 internal constant FEE_DENOMINATOR = 10000;

    /// @notice The address of our base token (VELO v2)
    IERC20 public constant velo =
        IERC20(0x9560e827aF36c94D2Ac33a39bCE1Fe78631088Db);

    /// @notice Token0 in our pool.
    IERC20 public poolToken0;

    /// @notice Token1 in our pool.
    IERC20 public poolToken1;

    /// @notice Factory address that deployed our Velodrome pool.
    address public factory;

    /// @notice True if our pool is stable, false if volatile.
    bool public isStablePool;

    /// @notice Array of structs containing our swap route to go from VELO to token0.
    /// @dev Struct is from token, to token, and true/false for stable/volatile.
    IVelodromeRouter.Routes[] public swapRouteForToken0;

    /// @notice Array of structs containing our swap route to go from VELO to token1.
    /// @dev Struct is from token, to token, and true/false for stable/volatile.
    IVelodromeRouter.Routes[] public swapRouteForToken1;

    /// @notice Minimum profit size in USDC that we want to harvest.
    /// @dev Only used in harvestTrigger.
    uint256 public harvestProfitMinInUsdc;

    /// @notice Maximum profit size in USDC that we want to harvest (ignore gas price once we get here).
    /// @dev Only used in harvestTrigger.
    uint256 public harvestProfitMaxInUsdc;

    /// @notice Will only be true on the original deployed contract and not on clones; we don't want to clone a clone.
    bool public isOriginal = true;

    // we use this to be able to adjust our strategy's name
    string internal stratName;

    /* ========== CONSTRUCTOR ========== */

    constructor(
        address _vault,
        address _gauge,
        IVelodromeRouter.Routes[] memory _veloSwapRouteForToken0,
        IVelodromeRouter.Routes[] memory _veloSwapRouteForToken1
    ) BaseStrategy(_vault) {
        _initializeStrat(
            _gauge,
            _veloSwapRouteForToken0,
            _veloSwapRouteForToken1
        );
    }

    /* ========== CLONING ========== */

    event Cloned(address indexed clone);

    /// @notice Use this to clone an exact copy of this strategy on another vault.
    /// @dev In practice, this will only be called by the factory on the template contract.
    /// @param _vault Vault address we are targeting with this strategy.
    /// @param _strategist Address to grant the strategist role.
    /// @param _rewards If we have any strategist rewards, send them here.
    /// @param _keeper Address to grant the keeper role.
    /// @param _gauge Gauge address for this strategy.
    /// @param _veloSwapRouteForToken0 Array of structs containing our swap route to go from VELO to token0.
    /// @param _veloSwapRouteForToken1 Array of structs containing our swap route to go from VELO to token1.
    /// @return newStrategy Address of our new cloned strategy.
    function cloneStrategyVelodrome(
        address _vault,
        address _strategist,
        address _rewards,
        address _keeper,
        address _gauge,
        IVelodromeRouter.Routes[] memory _veloSwapRouteForToken0,
        IVelodromeRouter.Routes[] memory _veloSwapRouteForToken1
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

        StrategyVelodromeFactoryClonable(newStrategy).initialize(
            _vault,
            _strategist,
            _rewards,
            _keeper,
            _gauge,
            _veloSwapRouteForToken0,
            _veloSwapRouteForToken1
        );

        emit Cloned(newStrategy);
    }

    /// @notice Initialize the strategy.
    /// @dev This should only be called by the clone function above.
    /// @param _vault Vault address we are targeting with this strategy.
    /// @param _strategist Address to grant the strategist role.
    /// @param _rewards If we have any strategist rewards, send them here.
    /// @param _keeper Address to grant the keeper role.
    /// @param _gauge Gauge address for this strategy.
    /// @param _veloSwapRouteForToken0 Array of structs containing our swap route to go from VELO to token0.
    /// @param _veloSwapRouteForToken1 Array of structs containing our swap route to go from VELO to token1.
    function initialize(
        address _vault,
        address _strategist,
        address _rewards,
        address _keeper,
        address _gauge,
        IVelodromeRouter.Routes[] memory _veloSwapRouteForToken0,
        IVelodromeRouter.Routes[] memory _veloSwapRouteForToken1
    ) public {
        _initialize(_vault, _strategist, _rewards, _keeper);
        _initializeStrat(
            _gauge,
            _veloSwapRouteForToken0,
            _veloSwapRouteForToken1
        );
    }

    // this is called by our original strategy, as well as any clones
    function _initializeStrat(
        address _gauge,
        IVelodromeRouter.Routes[] memory _veloSwapRouteForToken0,
        IVelodromeRouter.Routes[] memory _veloSwapRouteForToken1
    ) internal {
        // make sure that we haven't initialized this before
        if (address(gauge) != address(0)) {
            revert("already initialized");
        }

        // gauge, giver of life and VELO
        gauge = IVelodromeGauge(_gauge);

        // make sure we have the right gauge for our want
        if (gauge.stakingToken() != address(want)) {
            revert("gauge pool mismatch");
        }

        // check our pool to see if it is stable or volatile, get pool tokens as well (pool = want)
        IVelodromePool pool = IVelodromePool(address(want));
        isStablePool = pool.stable();
        poolToken0 = IERC20(pool.token0());
        poolToken1 = IERC20(pool.token1());
        factory = pool.factory();

        // create our route state vars
        for (uint i; i < _veloSwapRouteForToken0.length; ++i) {
            swapRouteForToken0.push(_veloSwapRouteForToken0[i]);
        }

        for (uint i; i < _veloSwapRouteForToken1.length; ++i) {
            swapRouteForToken1.push(_veloSwapRouteForToken1[i]);
        }

        // check our swap paths end with our correct token, but only if it's not VELO
        if (
            address(poolToken0) != address(velo) &&
            address(poolToken0) !=
            swapRouteForToken0[_veloSwapRouteForToken0.length - 1].to
        ) {
            revert("token0 route error");
        }

        if (
            address(poolToken1) != address(velo) &&
            address(poolToken1) !=
            swapRouteForToken1[_veloSwapRouteForToken1.length - 1].to
        ) {
            revert("token1 route error");
        }

        // set up our baseStrategy vars
        maxReportDelay = 30 days;
        creditThreshold = 50_000e18;
        harvestProfitMinInUsdc = 1_000e6;
        harvestProfitMaxInUsdc = 100_000e6;

        // want = Curve LP
        want.approve(_gauge, type(uint256).max);
        poolToken0.approve(address(router), type(uint256).max);
        poolToken1.approve(address(router), type(uint256).max);
        velo.approve(address(router), type(uint256).max);

        // set our strategy's name
        stratName = string(
            abi.encodePacked(
                "StrategyVelodromeFactory-",
                IDetails(address(want)).symbol()
            )
        );
    }

    /* ========== VIEWS ========== */

    /// @notice Strategy name.
    function name() external view override returns (string memory) {
        return stratName;
    }

    /// @notice Balance of want staked in Curve's gauge.
    function stakedBalance() public view returns (uint256) {
        return gauge.balanceOf(address(this));
    }

    /// @notice Balance of want sitting in our strategy.
    function balanceOfWant() public view returns (uint256) {
        return want.balanceOf(address(this));
    }

    /// @notice Total assets the strategy holds, sum of loose and staked want.
    function estimatedTotalAssets() public view override returns (uint256) {
        return balanceOfWant() + stakedBalance();
    }

    /// @notice Claimable VELO rewards. There can be other gauge rewards, but this is what we use for triggering harvests.
    function claimableRewards() public view returns (uint256) {
        return gauge.earned(address(this));
    }

    /// @notice Use this to check our current swap route of VELO to token0.
    /// @dev Since this is a factory, users may set non-optimal paths or liquidity may change over time.
    /// @return Array of tokens we swap through.
    function veloRouteToToken0() external view returns (address[] memory) {
        IVelodromeRouter.Routes[] memory _route = swapRouteForToken0;
        return _veloToRoute(_route);
    }

    /// @notice Use this to check our current swap route of VELO to token1.
    /// @dev Since this is a factory, users may set non-optimal paths or liquidity may change over time.
    /// @return Array of tokens we swap through.
    function veloRouteToToken1() external view returns (address[] memory) {
        IVelodromeRouter.Routes[] memory _route = swapRouteForToken1;
        return _veloToRoute(_route);
    }

    // credit to beefy for this useful helper function
    function _veloToRoute(
        IVelodromeRouter.Routes[] memory _route
    ) internal pure returns (address[] memory) {
        address[] memory route = new address[](_route.length + 1);
        route[0] = _route[0].from;
        for (uint i; i < _route.length; ++i) {
            route[i + 1] = _route[i].to;
        }
        return route;
    }

    /* ========== CORE STRATEGY FUNCTIONS ========== */

    function prepareReturn(
        uint256 _debtOutstanding
    )
        internal
        override
        returns (uint256 _profit, uint256 _loss, uint256 _debtPayment)
    {
        // harvest no matter what
        gauge.getReward(address(this));
        uint256 veloBalance = velo.balanceOf(address(this));

        // by default this is zero, but if we want any for our voter this will be used
        uint256 _localKeepVELO = localKeepVELO;
        address _veloVoter = veloVoter;
        if (_localKeepVELO > 0 && _veloVoter != address(0)) {
            uint256 sendToVoter;
            unchecked {
                sendToVoter = (veloBalance * _localKeepVELO) / FEE_DENOMINATOR;
            }
            if (sendToVoter > 0) {
                velo.safeTransfer(_veloVoter, sendToVoter);
            }
            veloBalance = velo.balanceOf(address(this));
        }

        // don't bother if we don't get at least 10 VELO
        if (veloBalance > 10e18) {
            // sell rewards for more want, have to add from both sides.
            uint256 amountToSwapToken0 = veloBalance / 2;
            uint256 amountToSwapToken1 = veloBalance - amountToSwapToken0;

            // if stable, do some more fancy math, not as easy as swapping half
            if (isStablePool) {
                uint256 ratio = router.quoteStableLiquidityRatio(
                    address(poolToken0),
                    address(poolToken1),
                    factory
                );
                amountToSwapToken1 = (veloBalance * ratio) / 1e18;
                amountToSwapToken0 = veloBalance - amountToSwapToken1;
            }

            if (address(poolToken0) != address(velo)) {
                router.swapExactTokensForTokens(
                    amountToSwapToken0,
                    0,
                    swapRouteForToken0,
                    address(this),
                    block.timestamp
                );
            }

            if (address(poolToken1) != address(velo)) {
                router.swapExactTokensForTokens(
                    amountToSwapToken1,
                    0,
                    swapRouteForToken1,
                    address(this),
                    block.timestamp
                );
            }

            // check and see what we have after swaps
            uint256 balanceToken0 = poolToken0.balanceOf(address(this));
            uint256 balanceToken1 = poolToken1.balanceOf(address(this));

            // deposit our liquidity, should have minimal remaining in strategy after this
            router.addLiquidity(
                address(poolToken0),
                address(poolToken1),
                isStablePool,
                balanceToken0,
                balanceToken1,
                1,
                1,
                address(this),
                block.timestamp
            );
        }

        // serious loss should never happen, but if it does (for instance, if Ramses is hacked), let's record it accurately
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

    function adjustPosition(uint256 _debtOutstanding) internal override {
        // if in emergency exit, we don't want to deploy any more funds
        if (emergencyExit) {
            return;
        }

        // Deposit all of our LP tokens in the gauge
        uint256 toInvest = balanceOfWant();
        if (toInvest > 0) {
            gauge.deposit(toInvest);
        }
    }

    function liquidatePosition(
        uint256 _amountNeeded
    ) internal override returns (uint256 _liquidatedAmount, uint256 _loss) {
        // check our loose want
        uint256 wantBal = balanceOfWant();
        if (_amountNeeded > wantBal) {
            uint256 stakedBal = stakedBalance();
            if (stakedBal > 0) {
                uint256 neededFromStaked;
                unchecked {
                    neededFromStaked = _amountNeeded - wantBal;
                }
                // withdraw whatever extra funds we need
                gauge.withdraw(Math.min(stakedBal, neededFromStaked));
            }
            uint256 withdrawnBal = balanceOfWant();
            _liquidatedAmount = Math.min(_amountNeeded, withdrawnBal);
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
        uint256 stakedBal = stakedBalance();
        if (stakedBal > 0) {
            // don't bother withdrawing zero, save gas where we can
            gauge.withdraw(stakedBal);
        }
        return balanceOfWant();
    }

    // migrate our want token to a new strategy if needed, as well as our CRV
    function prepareMigration(address _newStrategy) internal override {
        uint256 stakedBal = stakedBalance();
        if (stakedBal > 0) {
            gauge.withdraw(stakedBal);
        }
        uint256 veloBal = velo.balanceOf(address(this));

        if (veloBal > 0) {
            velo.safeTransfer(_newStrategy, veloBal);
        }
    }

    // want is blocked by default, add any other tokens to protect from gov here.
    function protectedTokens()
        internal
        view
        override
        returns (address[] memory)
    {}

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

        // harvest if we have a profit to claim at our upper limit without considering gas price
        uint256 claimableProfit = claimableProfitInUsdc();
        if (claimableProfit > harvestProfitMaxInUsdc) {
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

        // harvest if we have a sufficient profit to claim, but only if our gas price is acceptable
        if (claimableProfit > harvestProfitMinInUsdc) {
            return true;
        }

        StrategyParams memory params = vault.strategies(address(this));
        // harvest regardless of profit once we reach our maxDelay
        if (block.timestamp - params.lastReport > maxReportDelay) {
            return true;
        }

        // harvest our credit if it's above our threshold
        if (vault.creditAvailable() > creditThreshold) {
            return true;
        }

        // otherwise, we don't harvest
        return false;
    }

    /// @notice Calculates the profit if all claimable VELO were sold for USDC (6 decimals).
    /// @dev Calls Velodrome's VELO-USDC pool directly.
    /// @return Total return in USDC from selling claimable VELO.
    function claimableProfitInUsdc() public view returns (uint256) {
        // check price on our VELOv2/USDC pool
        uint256 veloPrice = IVelodromePool(
            0x8134A2fDC127549480865fB8E5A9E8A8a95a54c5
        ).getAmountOut(1e18, address(velo));

        // Pool returns amount as 6 decimals, so multiply by claimable VELO and divide by VELO decimals (1e18)
        return (veloPrice * claimableRewards()) / 1e18;
    }

    /**
     * @notice
     *  Here we set various parameters to optimize our harvestTrigger.
     * @param _harvestProfitMinInUsdc The amount of profit (in USDC, 6 decimals)
     *  that will trigger a harvest if gas price is acceptable.
     * @param _harvestProfitMaxInUsdc The amount of profit in USDC that
     *  will trigger a harvest regardless of gas price.
     */
    function setHarvestTriggerParams(
        uint256 _harvestProfitMinInUsdc,
        uint256 _harvestProfitMaxInUsdc
    ) external onlyVaultManagers {
        harvestProfitMinInUsdc = _harvestProfitMinInUsdc;
        harvestProfitMaxInUsdc = _harvestProfitMaxInUsdc;
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
    /// @param _keepVelo Percent of each VELO harvest to send to our voter.
    function setLocalKeepVelo(uint256 _keepVelo) external onlyGovernance {
        if (_keepVelo > 10_000) {
            revert();
        }
        if (_keepVelo > 0 && veloVoter == address(0)) {
            revert();
        }
        localKeepVELO = _keepVelo;
    }

    /// @notice Use this to set or update our voter contracts.
    /// @dev For Velo strategies, this is where we send our keepVELO.
    ///  Only governance can set this.
    /// @param _veloVoter Address of our velodrome voter.
    function setVoter(address _veloVoter) external onlyGovernance {
        veloVoter = _veloVoter;
    }
}
